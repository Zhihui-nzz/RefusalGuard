import chromadb
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass
from collections import OrderedDict
import hashlib
from backend.config import settings


class _LRUCache:
    """简单 LRU 缓存，避免重复计算相同输入的嵌入向量"""
    def __init__(self, maxsize: int = 500):
        self.maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()

    def get(self, key: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
        self._cache[key] = value


_query_cache = _LRUCache(maxsize=500)


@dataclass
class KBResult:
    kb_confidence:   float  # 知识库匹配置信度（越高说明越像已知攻击）
    matched_entries: list   # 匹配到的知识条目
    is_out_of_domain: bool  # 是否超出系统知识边界


class KnowledgeBaseModule:
    def __init__(self):
        self._degraded = False
        try:
            self.client = chromadb.PersistentClient(
                path="./backend/data/knowledge_base/chroma_db"
            )
            self.collection = self.client.get_collection("security_knowledge")
        except Exception as e:
            print(f"[WARNING] ChromaDB 加载失败，已降级为空知识库: {e}")
            self.client = None
            self.collection = None
            self._degraded = True

        # self.embedder = SentenceTransformer(
        #     "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        # )
        
        self.embedder = SentenceTransformer(
            settings.kb_embed_model,          
            local_files_only=True,            
        )

    def query(self, text: str, n_results: int = 3) -> KBResult:
        # 降级模式：知识库不可用时返回保守默认值
        if self._degraded or self.collection is None:
            return KBResult(
                kb_confidence=0.3,
                matched_entries=[],
                is_out_of_domain=True,
            )

        # LRU 缓存：相同输入直接返回缓存结果
        cache_key = hashlib.md5(text.encode()).hexdigest()
        cached = _query_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            embedding = self.embedder.encode([text]).tolist()
            results = self.collection.query(
                query_embeddings=embedding,
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            distances = results["distances"][0]
            # ChromaDB cosine distance: 0=完全相同, 2=完全不同 → 转换为相似度
            similarities = [max(0.0, 1.0 - d) for d in distances]

            kb_confidence = max(similarities) if similarities else 0.0
            matched = []
            for i, meta in enumerate(results["metadatas"][0]):
                matched.append({
                    "source":     meta.get("source"),
                    "id":         meta.get("id"),
                    "title":      meta.get("title") or meta.get("name"),
                    "similarity": similarities[i],
                })

            # 最高相似度 < 0.3 → 超出知识边界（可能是新型攻击）
            is_out_of_domain = kb_confidence < 0.3

            result = KBResult(
                kb_confidence=kb_confidence,
                matched_entries=matched,
                is_out_of_domain=is_out_of_domain,
            )
            _query_cache.set(cache_key, result)
            return result

        except Exception as e:
            print(f"[WARNING] 知识库查询异常: {e}，返回默认值")
            return KBResult(
                kb_confidence=0.3,
                matched_entries=[],
                is_out_of_domain=True,
            )
