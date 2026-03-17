"""智谱知识库 API 封装：创建/上传/检索/删除"""
import json
import os
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://open.bigmodel.cn/api/llm-application/open"

# 支持上传的文件格式
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"}


class KnowledgeBaseManager:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")
        if not self.api_key:
            logger.warning("ZHIPU_API_KEY not set, knowledge base features disabled")
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # === 知识库管理 ===

    def create_kb(self, name: str, description: str = "", embedding_id: int = 12) -> str:
        """创建知识库。embedding_id: 12=Embedding-3-pro (默认最强)。返回 knowledge_id"""
        if not self.enabled:
            return ""
        resp = requests.post(
            f"{BASE_URL}/knowledge",
            headers=self.headers,
            json={"name": name, "description": description, "embedding_id": embedding_id},
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("data"):
            kb_id = data["data"].get("id", "")
            logger.info(f"Created knowledge base '{name}': {kb_id}")
            return str(kb_id)
        logger.error(f"Failed to create KB '{name}': {data}")
        return ""

    def list_kbs(self, page: int = 1, size: int = 50) -> list:
        """列出所有知识库"""
        if not self.enabled:
            return []
        resp = requests.get(
            f"{BASE_URL}/knowledge",
            headers=self.headers,
            params={"page": page, "size": size},
        )
        data = resp.json()
        return data.get("data", {}).get("list", [])

    def delete_kb(self, kb_id: str) -> bool:
        """删除知识库"""
        if not self.enabled:
            return False
        resp = requests.delete(f"{BASE_URL}/knowledge/{kb_id}", headers=self.headers)
        return resp.status_code == 200

    def find_kb_by_name(self, name: str) -> str:
        """按名称查找知识库，返回 ID，不存在则返回空字符串"""
        kbs = self.list_kbs()
        for kb in kbs:
            if kb.get("name") == name:
                return str(kb.get("id", ""))
        return ""

    def get_or_create_kb(self, name: str, description: str = "") -> str:
        """获取或创建知识库"""
        kb_id = self.find_kb_by_name(name)
        if kb_id:
            return kb_id
        return self.create_kb(name, description)

    # === 文档管理 ===

    def upload_document(self, kb_id: str, file_path: str, knowledge_type: int = 1,
                        skip_if_exists: bool = True, display_name: str = "") -> str:
        """上传文档到知识库。
        knowledge_type: 1=标题段落分段(默认), 5=自定义分段
        skip_if_exists: 按文件名检查是否已存在，避免重复上传
        display_name: 上传到知识库的文件名（默认用原文件名）
        返回 document_id
        """
        if not self.enabled:
            return ""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return ""

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning(f"Unsupported file type: {ext}, skipping {file_path}")
            return ""

        upload_name = display_name or os.path.basename(file_path)
        # display_name 需要保留原扩展名
        if display_name and not display_name.endswith(ext):
            upload_name = display_name + ext

        if skip_if_exists:
            existing_docs = self.list_documents(kb_id)
            for doc in existing_docs:
                doc_name = doc.get("name", "") or doc.get("document_name", "")
                if upload_name in doc_name:
                    logger.info(f"Document already exists, skipping: {upload_name}")
                    return doc.get("id", "")

        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{BASE_URL}/document/upload_document/{kb_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"files": (upload_name, f)},
                    data={"knowledge_type": str(knowledge_type)},
                )
            data = resp.json()
            if resp.status_code == 200 and data.get("code") == 200:
                # API 返回格式: data.successInfos[].documentId
                success = (data.get("data") or {}).get("successInfos", [])
                if success:
                    doc_id = success[0].get("documentId", "")
                    logger.info(f"Uploaded {os.path.basename(file_path)} -> {kb_id} (doc_id={doc_id})")
                    return str(doc_id)
                # 兼容旧格式
                doc_id = (data.get("data") or {}).get("id", "")
                if doc_id:
                    logger.info(f"Uploaded {os.path.basename(file_path)} -> {kb_id}")
                    return str(doc_id)
            logger.error(f"Upload failed for {file_path}: {data}")
        except Exception as e:
            logger.error(f"Upload error for {file_path}: {e}")
        return ""

    def list_documents(self, kb_id: str, page: int = 1, size: int = 50) -> list:
        """列出知识库中的文档"""
        if not self.enabled:
            return []
        resp = requests.get(
            f"{BASE_URL}/document",
            headers=self.headers,
            params={"knowledge_id": kb_id, "page": page, "size": size},
        )
        data = resp.json()
        return data.get("data", {}).get("list", [])

    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        if not self.enabled:
            return False
        resp = requests.delete(f"{BASE_URL}/document/{doc_id}", headers=self.headers)
        return resp.status_code == 200

    # === 检索 ===

    def retrieve(self, kb_ids: list, query: str, top_k: int = 8, recall_method: str = "mixed") -> list:
        """从知识库检索。
        recall_method: embedding | keyword | mixed(默认)
        返回 [{text, score, metadata}, ...]
        """
        if not self.enabled or not kb_ids:
            return []
        try:
            resp = requests.post(
                f"{BASE_URL}/knowledge/retrieve",
                headers={**self.headers, "Content-Type": "application/json"},
                json={
                    "knowledge_ids": kb_ids,
                    "query": query,
                    "top_k": top_k,
                    "recall_method": recall_method,
                },
            )
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Retrieve error: {e}")
            return []


SINGLE_KB_NAME = "archon_research"


def search_knowledge_base(query: str, scope: str = "all", top_k: int = 5) -> str:
    """搜索知识库中的历史中间结果。

    Args:
        query: 搜索内容
        scope: 搜索范围 - 按文件标题前缀过滤（如 T001, survey, dataset 等），all=全部
        top_k: 返回结果数

    Returns:
        检索结果 JSON 字符串
    """
    kb_mgr = KnowledgeBaseManager()
    if not kb_mgr.enabled:
        return json.dumps({"error": "Knowledge base not configured (ZHIPU_API_KEY missing)"})

    # 始终搜索单一知识库
    kb_id = kb_mgr.find_kb_by_name(SINGLE_KB_NAME)
    if not kb_id:
        return json.dumps({"results": [], "message": f"Knowledge base '{SINGLE_KB_NAME}' not found"})

    results = kb_mgr.retrieve([kb_id], query, top_k=top_k)

    # 按 scope 过滤结果（基于文件标题前缀）
    if scope != "all" and results:
        scope_upper = scope.upper()
        filtered = []
        for r in results:
            metadata = r.get("metadata", {}) if isinstance(r, dict) else {}
            doc_name = metadata.get("document_name", "") or str(r.get("document_name", ""))
            # 支持 scope 为 topic_id (T001) 或 phase (survey/dataset)
            if scope_upper in doc_name.upper() or f"[{scope}]" in doc_name:
                filtered.append(r)
        results = filtered

    return json.dumps(results, indent=2, ensure_ascii=False)
