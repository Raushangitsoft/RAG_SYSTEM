import os
import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Company Document AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1E3A5F 0%, #2E75B6 100%);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .source-card {
        background: #f0f4f8;
        border-left: 4px solid #2E75B6;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        margin: 0.4rem 0;
        font-size: 0.9rem;
    }
    .answer-box {
        background: #ffffff;
        border: 1px solid #e0e8f0;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        line-height: 1.7;
    }
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.8rem;
        text-align: center;
    }
    .status-badge-ok {
        background: #d1fae5; color: #065f46;
        padding: 2px 10px; border-radius: 12px; font-size: 0.8rem;
    }
    .status-badge-fail {
        background: #fee2e2; color: #991b1b;
        padding: 2px 10px; border-radius: 12px; font-size: 0.8rem;
    }
    .stButton > button {
        background: #2E75B6;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: #1E3A5F;
    }
</style>
""", unsafe_allow_html=True)


# ── Helper functions ───────────────────────────────────────────────────────────

def api_get(path: str, **kwargs):
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{BACKEND_URL}{path}", **kwargs)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return None


def api_post(path: str, timeout: int = 120, **kwargs):
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(f"{BACKEND_URL}{path}", **kwargs)
            r.raise_for_status()
            return r.json(), None
    except httpx.HTTPStatusError as e:
        return None, e.response.json().get("detail", str(e))
    except Exception as e:
        return None, str(e)


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📚 Document AI")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        ["💬 Ask Documents", "📁 Manage Documents", "📊 Query History", "🔧 System Status"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Department filter
    st.markdown("### Filter")
    department_filter = st.selectbox(
        "Department",
        ["all", "hr", "finance", "legal", "it", "operations", "general"],
        index=0,
    )

    st.markdown("---")
    st.markdown("**System Info**")
    health = api_get("/health")
    if health and health.get("status") == "ok":
        st.success("Backend: Online")
    else:
        st.error("Backend: Offline")


# ── Page: Ask Documents ────────────────────────────────────────────────────────

if "💬 Ask Documents" in page:
    st.markdown("""
    <div class="main-header">
        <h2 style="margin:0">💬 Ask Your Company Documents</h2>
        <p style="margin:0.3rem 0 0;opacity:0.85">Powered by Hybrid RAG — Semantic + Keyword Search</p>
    </div>
    """, unsafe_allow_html=True)

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and "sources" in msg:
                if msg["sources"]:
                    with st.expander(f"📎 {len(msg['sources'])} source(s) cited"):
                        for src in msg["sources"]:
                            st.markdown(f"""<div class="source-card">
                                📄 <b>{src['document_name']}</b> — Page {src['page_number']}<br>
                                <span style="color:#666;font-size:0.85rem">{src.get('section_heading','')}</span>
                            </div>""", unsafe_allow_html=True)

    # Query input
    query = st.chat_input("Ask a question about company documents...")

    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Searching documents..."):
                dept = department_filter if department_filter != "all" else None
                result, error = api_post(
                    "/api/v1/query/",
                    timeout=600,
                    json={"query": query, "department": dept},
                )

            if error:
                st.error(f"Error: {error}")
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {error}", "sources": []})
            elif result:
                answer = result["answer"]
                st.markdown(answer)

                # Metadata row
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("⏱ Latency", f"{result['latency_ms']}ms")
                col2.metric("📦 Chunks Used", result["chunk_count"])
                col3.metric("🔍 Mode", "Cached" if result["from_cache"] else "Live")
                if result.get("rewritten_query") != query:
                    col4.metric("✏️ Rewritten", "Yes")

                sources = result.get("sources", [])
                if sources:
                    with st.expander(f"📎 {len(sources)} source(s) cited"):
                        for src in sources:
                            st.markdown(f"""<div class="source-card">
                                📄 <b>{src['document_name']}</b> — Page {src['page_number']}<br>
                                <span style="color:#666;font-size:0.85rem">{src.get('section_heading','')}</span>
                            </div>""", unsafe_allow_html=True)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources,
                })

    if st.button("🗑 Clear Chat"):
        st.session_state.messages = []
        st.rerun()


# ── Page: Manage Documents ─────────────────────────────────────────────────────

elif "📁 Manage Documents" in page:
    st.markdown("""
    <div class="main-header">
        <h2 style="margin:0">📁 Document Management</h2>
        <p style="margin:0.3rem 0 0;opacity:0.85">Upload, view, and manage indexed documents</p>
    </div>
    """, unsafe_allow_html=True)

    # Upload section
    with st.expander("📤 Upload New Document", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            uploaded_file = st.file_uploader(
                "Choose a file",
                type=["pdf", "docx", "pptx", "xlsx", "txt"],
            )
            dept = st.selectbox("Department", ["general", "hr", "finance", "legal", "it", "operations"])
        with col2:
            owner = st.text_input("Owner / Uploader", value="admin")
            confidentiality = st.selectbox("Confidentiality", ["public", "internal", "restricted", "confidential"])
            tags = st.text_input("Tags (comma-separated)", placeholder="policy, 2024, hr")

        if st.button("📤 Upload & Index"):
            if not uploaded_file:
                st.warning("Please select a file first.")
            else:
                with st.spinner("Uploading and starting indexing..."):
                    try:
                        with httpx.Client(timeout=60) as client:
                            r = client.post(
                                f"{BACKEND_URL}/api/v1/documents/upload",
                                files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
                                data={
                                    "department": dept,
                                    "owner": owner,
                                    "confidentiality": confidentiality,
                                    "tags": tags,
                                },
                            )
                            if r.status_code == 200:
                                st.success(f"✅ Uploaded! Indexing running in background.")
                                st.json(r.json())
                            else:
                                st.error(f"Upload failed: {r.json().get('detail', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"Upload failed: {e}")

    st.markdown("---")

    # Document list
    st.markdown("### 📋 Indexed Documents")

    dept_param = department_filter if department_filter != "all" else None
    params = {}
    if dept_param:
        params["department"] = dept_param

    docs = api_get("/api/v1/documents/", params=params)

    if not docs:
        st.info("No documents found. Upload your first document above.")
    else:
        st.markdown(f"**{len(docs)} document(s) found**")
        for doc in docs:
            status_color = {
                "indexed": "🟢", "processing": "🟡",
                "pending": "⚪", "failed": "🔴", "deleted": "⚫"
            }.get(doc["status"], "⚪")

            with st.expander(f"{status_color} {doc['original_name']} — {doc['department'].upper()}"):
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**ID:** `{doc['id'][:8]}...`")
                col1.markdown(f"**Status:** {doc['status']}")
                col2.markdown(f"**Chunks:** {doc['chunk_count']}")
                col2.markdown(f"**Owner:** {doc['owner']}")
                col3.markdown(f"**Confidentiality:** {doc['confidentiality']}")
                col3.markdown(f"**Uploaded:** {doc['created_at'][:10]}")

                if doc.get("indexed_at"):
                    st.markdown(f"*Indexed at: {doc['indexed_at'][:19]}*")

                bcol1, bcol2 = st.columns(2)
                if bcol1.button("🔄 Reindex", key=f"reindex_{doc['id']}"):
                    result, err = api_post(f"/api/v1/documents/{doc['id']}/reindex")
                    if err:
                        st.error(err)
                    else:
                        st.success("Reindexing started!")
                        st.rerun()

                if bcol2.button("🗑 Delete", key=f"del_{doc['id']}"):
                    with httpx.Client(timeout=30) as client:
                        r = client.delete(f"{BACKEND_URL}/api/v1/documents/{doc['id']}")
                        if r.status_code == 200:
                            st.success("Deleted!")
                            st.rerun()
                        else:
                            st.error("Delete failed")


# ── Page: Query History ────────────────────────────────────────────────────────

elif "📊 Query History" in page:
    st.markdown("""
    <div class="main-header">
        <h2 style="margin:0">📊 Query History</h2>
        <p style="margin:0.3rem 0 0;opacity:0.85">Recent queries and response metrics</p>
    </div>
    """, unsafe_allow_html=True)

    history = api_get("/api/v1/query/history", params={"limit": 30})
    if not history:
        st.info("No query history yet.")
    else:
        # Summary metrics
        total = len(history)
        success = sum(1 for h in history if h["status"] == "success")
        avg_latency = sum(h["latency_ms"] or 0 for h in history) // max(total, 1)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Queries", total)
        col2.metric("Success Rate", f"{int(success/total*100)}%")
        col3.metric("Avg Latency", f"{avg_latency}ms")

        st.markdown("---")

        for h in history:
            status_icon = "✅" if h["status"] == "success" else "❌"
            with st.expander(f"{status_icon} {h['query'][:80]}... — {h['created_at'][:16]}"):
                st.markdown(f"**Answer:** {(h.get('answer') or 'No answer')[:300]}...")
                col1, col2 = st.columns(2)
                col1.markdown(f"**Latency:** {h.get('latency_ms', '—')}ms")
                col2.markdown(f"**Chunks:** {h.get('chunk_count', '—')}")


# ── Page: System Status ────────────────────────────────────────────────────────

elif "🔧 System Status" in page:
    st.markdown("""
    <div class="main-header">
        <h2 style="margin:0">🔧 System Status</h2>
        <p style="margin:0.3rem 0 0;opacity:0.85">Health of all system components</p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Refresh Status"):
        st.rerun()

    health = api_get("/health/detailed")
    if not health:
        st.error("Cannot reach backend. Is it running?")
    else:
        overall = health.get("status", "unknown")
        if overall == "ok":
            st.success("✅ All systems operational")
        else:
            st.warning("⚠️ Some services are degraded")

        services = health.get("services", {})
        cols = st.columns(len(services))

        icons = {
            "redis": "🗄️ Redis",
            "qdrant": "🔷 Qdrant",
            "elasticsearch": "🔍 Elasticsearch",
            "ollama": "🤖 Ollama LLM",
        }

        for col, (service, ok) in zip(cols, services.items()):
            label = icons.get(service, service.title())
            with col:
                if ok:
                    st.markdown(f"""<div class="metric-card">
                        <div style="font-size:2rem">✅</div>
                        <div style="font-weight:600">{label}</div>
                        <div><span class="status-badge-ok">Online</span></div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div class="metric-card">
                        <div style="font-size:2rem">❌</div>
                        <div style="font-weight:600">{label}</div>
                        <div><span class="status-badge-fail">Offline</span></div>
                    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📖 API Documentation")
    st.markdown(f"Swagger UI: [{BACKEND_URL}/docs]({BACKEND_URL}/docs)")
    st.markdown(f"ReDoc: [{BACKEND_URL}/redoc]({BACKEND_URL}/redoc)")
