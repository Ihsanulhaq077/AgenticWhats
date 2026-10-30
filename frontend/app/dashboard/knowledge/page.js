"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api";

export default function KnowledgePage() {
  const [docs, setDocs] = useState([]);
  const [form, setForm] = useState({ title: "", content: "" });
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  async function load() {
    try { setDocs(await api.get("/api/knowledge")); } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function addDoc(e) {
    e.preventDefault();
    setError("");
    const fd = new FormData();
    fd.append("title", form.title);
    fd.append("content", form.content);
    fd.append("source_type", "text");
    try {
      await api.postForm("/api/knowledge/documents", fd);
      setForm({ title: "", content: "" });
      await load();
    } catch (e2) { setError(e2.message); }
  }

  async function uploadFile(e) {
    e.preventDefault();
    if (!fileRef.current?.files?.[0]) return;
    setError("");
    const fd = new FormData();
    fd.append("file", fileRef.current.files[0]);
    try {
      await api.postForm("/api/knowledge/upload", fd);
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (e2) { setError(e2.message); }
  }

  async function search(e) {
    e.preventDefault();
    const fd = new FormData();
    fd.append("query", query);
    setResults(await api.postForm("/api/knowledge/search", fd));
  }

  async function remove(id) {
    await api.delete(`/api/knowledge/${id}`);
    await load();
  }

  async function reindex() {
    await api.post("/api/knowledge/reindex");
    await load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Knowledge Base (RAG)</h1>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="grid md:grid-cols-2 gap-6">
        <form onSubmit={addDoc} className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <h2 className="text-sm font-semibold">Add text / FAQ document</h2>
          <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Title, e.g. Delivery Policy"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <textarea required rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })}
            placeholder={"Q: What time do you open?\nA: We open at 11 AM daily.\n\nQ: …\nA: …"}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono" />
          <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">
            Save & index
          </button>
        </form>

        <div className="space-y-6">
          <form onSubmit={uploadFile} className="bg-white rounded-xl border border-gray-200 p-4">
            <h2 className="text-sm font-semibold mb-2">Upload file (.txt, .md, .csv, .json — max 2 MB)</h2>
            <div className="flex gap-2">
              <input ref={fileRef} type="file" accept=".txt,.md,.csv,.json"
                className="text-sm flex-1" />
              <button type="submit" className="px-4 py-2 rounded-lg bg-gray-800 text-white text-sm hover:bg-black">
                Upload
              </button>
            </div>
          </form>

          <form onSubmit={search} className="bg-white rounded-xl border border-gray-200 p-4">
            <h2 className="text-sm font-semibold mb-2">Test retrieval</h2>
            <div className="flex gap-2">
              <input value={query} onChange={(e) => setQuery(e.target.value)} required
                placeholder="e.g. delivery charges"
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700">
                Search
              </button>
            </div>
            {results !== null && (
              <div className="mt-3 space-y-2">
                {results.length === 0 && <p className="text-xs text-gray-500">No matches.</p>}
                {results.map((r) => (
                  <div key={r.chunk_id} className="text-xs bg-gray-50 rounded-lg p-3">
                    <span className="font-mono text-emerald-700">score {r.score}</span>
                    <p className="mt-1 whitespace-pre-wrap">{r.content}</p>
                  </div>
                ))}
              </div>
            )}
          </form>
        </div>
      </div>

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Documents</h2>
        <button onClick={reindex} className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200">
          Re-index all
        </button>
      </div>
      <div className="mt-3 bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        {docs.map((d) => (
          <div key={d.id} className="flex items-center justify-between p-4">
            <div>
              <div className="text-sm font-medium">{d.title}
                <span className="ml-2 text-[10px] text-gray-400">v{d.version}</span>
              </div>
              <div className="text-xs text-gray-500">
                {d.source_type} · {d.chunk_count} chunks · {new Date(d.created_at).toLocaleDateString()}
              </div>
            </div>
            <button onClick={() => remove(d.id)} className="text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100">
              Delete
            </button>
          </div>
        ))}
        {docs.length === 0 && <p className="text-sm text-gray-500 p-4">No documents yet.</p>}
      </div>
    </div>
  );
}
