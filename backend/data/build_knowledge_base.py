import chromadb
import json
import requests
from sentence_transformers import SentenceTransformer
from loguru import logger

# OWASP LLM Top 10 
OWASP_LLM_TOP10 = [
    {
        "id": "LLM01",
        "title": "Prompt Injection",
        "description": "Attackers manipulate LLMs through crafted inputs, causing the LLM to execute unintended actions. Direct injections overwrite system prompts, while indirect injections manipulate inputs from external sources.",
        "examples": ["Ignore previous instructions", "You are now DAN", "Forget your guidelines"]
    },
    {
        "id": "LLM02", 
        "title": "Insecure Output Handling",
        "description": "Insufficient validation of LLM outputs before passing downstream. Can lead to XSS, CSRF, SSRF, privilege escalation, or remote code execution.",
        "examples": ["LLM generates malicious JavaScript", "SQL injection via LLM output"]
    },
    {
        "id": "LLM06",
        "title": "Sensitive Information Disclosure",
        "description": "LLMs may reveal confidential data, proprietary algorithms, or personal information in responses. Risk increases with training data memorization.",
        "examples": ["Extract system prompt", "Reveal training data", "Expose API keys"]
    },
    {
        "id": "LLM07",
        "title": "Insecure Plugin Design",
        "description": "LLM plugins with insecure inputs or insufficient access control. Malicious actors can exploit these to perform remote code execution or data exfiltration.",
        "examples": ["Plugin with no input validation", "Excessive permissions granted to plugin"]
    },
]

# MITRE ATT&CK for Enterprise - AI/ML 相关技术
MITRE_AI_TECHNIQUES = [
    {
        "id": "T1059",
        "name": "Command and Scripting Interpreter",
        "description": "Adversaries may abuse command and script interpreters to execute commands, scripts, or binaries. Prompt injection can be used to trigger code execution through LLM tool use.",
        "tactic": "Execution"
    },
    {
        "id": "T1190",
        "name": "Exploit Public-Facing Application",
        "description": "Adversaries may attempt to exploit weaknesses in internet-facing LLM applications. Prompt injection represents a novel attack surface for this technique.",
        "tactic": "Initial Access"
    },
    {
        "id": "T1530",
        "name": "Data from Cloud Storage",
        "description": "Adversaries may access data from cloud storage via LLM tool calls triggered by prompt injection attacks.",
        "tactic": "Collection"
    },
    {
        "id": "T1566",
        "name": "Phishing",
        "description": "LLMs can be exploited to craft highly convincing phishing content or to process malicious content embedded in documents.",
        "tactic": "Initial Access"
    },
]

def build_knowledge_base():
    logger.info("初始化 ChromaDB...")
    client = chromadb.PersistentClient(path="./backend/data/knowledge_base/chroma_db")
    
    # 删除旧集合
    try:
        client.delete_collection("security_knowledge")
    except Exception:
        pass
    
    collection = client.create_collection(
        name="security_knowledge",
        metadata={"hnsw:space": "cosine"}
    )
    
    logger.info("加载嵌入模型...")
    # 使用多语言模型，支持中英文检索
    embedder = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    
    documents = []
    metadatas = []
    ids = []
    
    # 添加 OWASP 数据
    for item in OWASP_LLM_TOP10:
        doc = f"{item['title']}: {item['description']} Examples: {', '.join(item['examples'])}"
        documents.append(doc)
        metadatas.append({"source": "OWASP_LLM", "id": item["id"], "title": item["title"]})
        ids.append(f"owasp_{item['id']}")
    
    # 添加 MITRE 数据
    for item in MITRE_AI_TECHNIQUES:
        doc = f"{item['name']} ({item['tactic']}): {item['description']}"
        documents.append(doc)
        metadatas.append({"source": "MITRE_ATTACK", "id": item["id"], "name": item["name"]})
        ids.append(f"mitre_{item['id']}")
    
    logger.info(f"正在向量化 {len(documents)} 条知识条目...")
    embeddings = embedder.encode(documents, show_progress_bar=True).tolist()
    
    collection.add(documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids)
    logger.info(f"知识库构建完成，共 {len(documents)} 条记录")

if __name__ == "__main__":
    build_knowledge_base()