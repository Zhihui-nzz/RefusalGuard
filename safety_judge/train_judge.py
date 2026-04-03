"""
RefusalGuard Safety Judge — 训练脚本 v1.3
=========================================
模型  : microsoft/deberta-v3-base（~184M 参数）
任务  : 三分类
        0 = benign        (正常请求)
        1 = injection     (提示注入 / 越狱)
        2 = harmful       (有害内容，非注入类)
硬件  : NVIDIA RTX 4060（8GB VRAM）

运行方式：
    python safety_judge/train_judge.py --smoke_test   # 冒烟测试
    python safety_judge/train_judge.py                # 正式训练

v1.3 修复记录：
    - 放弃 FP16/BF16 混合精度，改用纯 FP32 训练。
      DeBERTa-v3 的 safetensors 权重为 BF16，加载后模型参数为 bfloat16，
      autocast 会让 logits 保持 half/bfloat16，而 CrossEntropyLoss 的
      weight_tensor 是 float32，两者类型不匹配导致崩溃。
      最稳妥的方案：加载模型后立即 .float() 转为 FP32，全程 FP32 训练。
      RTX 4060 显存 8.6GB，FP32 训练 DeBERTa-v3-base (batch=16) 完全够用。
    - DataLoader num_workers=0（Windows spawn 多进程问题）
    - 日志每 step 都打印，方便观察训练进度
"""

import argparse
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    get_cosine_schedule_with_warmup,
)
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_class_weight
from loguru import logger

# ─── 命令行参数 ────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent

parser = argparse.ArgumentParser()
parser.add_argument("--model_name",   default="microsoft/deberta-v3-base")
parser.add_argument("--data_dir",     default=str(_SCRIPT_DIR / "data"))
parser.add_argument("--output_dir",   default=str(_SCRIPT_DIR / "model"))
parser.add_argument("--max_len",      type=int,   default=256)
parser.add_argument("--batch_size",   type=int,   default=16)
parser.add_argument("--epochs",       type=int,   default=5)
parser.add_argument("--lr",           type=float, default=2e-5)
parser.add_argument("--warmup_ratio", type=float, default=0.1)
parser.add_argument("--patience",     type=int,   default=3)
parser.add_argument("--smoke_test",   action="store_true",
                    help="冒烟测试：只用 100 条样本跑 1 个 epoch")
args = parser.parse_args()

DATA_DIR   = Path(args.data_dir)
OUTPUT_DIR = Path(args.output_dir)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Windows 多进程 spawn 模式会重复执行顶层代码，强制设为 0
NUM_WORKERS = 0 if platform.system() == "Windows" else 4

logger.info(f"Device      : {DEVICE}")
if DEVICE == "cuda":
    logger.info(f"GPU         : {torch.cuda.get_device_name(0)}")
    logger.info(f"VRAM        : {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
logger.info(f"Precision   : FP32（全精度，最稳定）")
logger.info(f"num_workers : {NUM_WORKERS}")


# ─── 数据集 ────────────────────────────────────────────────────────────────
class SafetyDataset(Dataset):
    def __init__(self, path: Path, tokenizer, max_len: int, limit: int = None):
        self.samples = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                self.samples.append((obj["text"], int(obj["label"])))
        if limit:
            self.samples = self.samples[:limit]
        self.tokenizer = tokenizer
        self.max_len   = max_len

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        text, label = self.samples[idx]
        enc = self.tokenizer(
            text,
            max_length=self.max_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids":      enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "label":          torch.tensor(label, dtype=torch.long),
        }


# ─── 评估函数 ──────────────────────────────────────────────────────────────
def evaluate(model, loader, device, criterion):
    model.eval()
    all_preds, all_labels = [], []
    total_loss = 0.0
    with torch.no_grad():
        for batch in loader:
            ids    = batch["input_ids"].to(device)
            mask   = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)
            out    = model(input_ids=ids, attention_mask=mask)
            # logits 和 criterion 均为 FP32，类型一致，不会报错
            loss   = criterion(out.logits, labels)
            total_loss += loss.item()
            preds = out.logits.argmax(dim=-1).cpu().numpy()
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.cpu().numpy().tolist())
    avg_loss = total_loss / len(loader)
    macro_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    return avg_loss, macro_f1, all_preds, all_labels


# ─── 主训练流程 ────────────────────────────────────────────────────────────
def main():
    logger.info(f"Loading tokenizer: {args.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    limit = 100 if args.smoke_test else None
    logger.info(f"Loading datasets (limit={limit}) ...")
    train_ds = SafetyDataset(DATA_DIR / "train.jsonl", tokenizer, args.max_len, limit=limit)
    val_ds   = SafetyDataset(DATA_DIR / "val.jsonl",   tokenizer, args.max_len, limit=limit)
    test_ds  = SafetyDataset(DATA_DIR / "test.jsonl",  tokenizer, args.max_len, limit=limit)
    logger.info(f"  train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}")

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=(DEVICE == "cuda"),
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=(DEVICE == "cuda"),
    )
    test_loader = DataLoader(
        test_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=(DEVICE == "cuda"),
    )

    # 类别权重（处理不平衡）—— 保持 float32
    all_labels    = [s[1] for s in train_ds.samples]
    classes       = np.array(sorted(set(all_labels)))
    weights       = compute_class_weight("balanced", classes=classes, y=all_labels)
    weight_tensor = torch.tensor(weights, dtype=torch.float32).to(DEVICE)
    logger.info(f"Class weights: { {int(c): round(float(w), 4) for c, w in zip(classes, weights)} }")

    logger.info(f"Loading model: {args.model_name}")
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=3,
        use_safetensors=True,
    )
    # ★ 关键修复：将模型参数从 bfloat16 转为 float32，
    #   确保 logits 与 weight_tensor（float32）类型一致，避免 CrossEntropyLoss 崩溃。
    model = model.float().to(DEVICE)
    logger.info(f"  Model dtype: {next(model.parameters()).dtype}")  # 应输出 torch.float32

    optimizer     = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    epochs_to_run = 1 if args.smoke_test else args.epochs
    total_steps   = len(train_loader) * epochs_to_run
    warmup_steps  = int(total_steps * args.warmup_ratio)
    scheduler     = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )
    criterion = torch.nn.CrossEntropyLoss(weight=weight_tensor)

    best_val_f1  = 0.0
    patience_cnt = 0
    history      = []

    for epoch in range(1, epochs_to_run + 1):
        model.train()
        epoch_loss = 0.0
        t0 = time.time()

        for step, batch in enumerate(train_loader, 1):
            ids    = batch["input_ids"].to(DEVICE)
            mask   = batch["attention_mask"].to(DEVICE)
            labels = batch["label"].to(DEVICE)

            optimizer.zero_grad()
            out  = model(input_ids=ids, attention_mask=mask)
            loss = criterion(out.logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            epoch_loss += loss.item()

            if step % 10 == 0 or step == len(train_loader):
                logger.info(
                    f"  Epoch {epoch} | Step {step}/{len(train_loader)} | "
                    f"loss={epoch_loss / step:.4f}"
                )

        train_avg_loss = epoch_loss / len(train_loader)
        val_loss, val_f1, _, _ = evaluate(model, val_loader, DEVICE, criterion)
        elapsed = time.time() - t0

        logger.info(
            f"Epoch {epoch}/{epochs_to_run} | "
            f"train_loss={train_avg_loss:.4f} | "
            f"val_loss={val_loss:.4f} | "
            f"val_macro_f1={val_f1:.4f} | "
            f"elapsed={elapsed:.1f}s"
        )
        history.append({
            "epoch":      epoch,
            "train_loss": round(train_avg_loss, 4),
            "val_loss":   round(val_loss, 4),
            "val_f1":     round(val_f1, 4),
            "elapsed_s":  round(elapsed, 1),
        })

        if val_f1 > best_val_f1:
            best_val_f1  = val_f1
            patience_cnt = 0
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            logger.info(f"  ✓ Best model saved (val_f1={best_val_f1:.4f})")
        else:
            patience_cnt += 1
            logger.info(f"  No improvement ({patience_cnt}/{args.patience})")
            if patience_cnt >= args.patience:
                logger.info("Early stopping triggered.")
                break

    # ─── 测试集评估 ──────────────────────────────────────────────────────
    logger.info("\nLoading best model for test evaluation ...")
    best_model = AutoModelForSequenceClassification.from_pretrained(
        OUTPUT_DIR,
        num_labels=3,
    ).float().to(DEVICE)

    test_loss, test_f1, test_preds, test_labels = evaluate(
        best_model, test_loader, DEVICE, criterion
    )

    label_names = ["benign", "injection", "harmful"]
    report = classification_report(
        test_labels, test_preds, target_names=label_names, digits=4, zero_division=0
    )
    cm = confusion_matrix(test_labels, test_preds)

    logger.info(f"\nTest Results:")
    logger.info(f"  test_loss     = {test_loss:.4f}")
    logger.info(f"  test_macro_f1 = {test_f1:.4f}")
    logger.info(f"\nClassification Report:\n{report}")
    logger.info(f"\nConfusion Matrix:\n{cm}")

    results = {
        "best_val_f1":           round(best_val_f1, 4),
        "test_loss":             round(test_loss, 4),
        "test_macro_f1":         round(test_f1, 4),
        "history":               history,
        "classification_report": report,
        "confusion_matrix":      cm.tolist(),
    }
    with open(OUTPUT_DIR / "eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info(f"\nAll results saved to {OUTPUT_DIR}")
    logger.info("Training complete.")


if __name__ == "__main__":
    main()
