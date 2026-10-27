import { useState, useEffect, useRef, useCallback } from "react";
import { uploadDocuments, listDocuments, deleteDocument } from "../api";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef(null);

  const loadDocuments = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await listDocuments();
      setDocuments(data);
      setError("");
    } catch (err) {
      if (!silent) setError("Failed to load documents: " + err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Auto-refresh when any document is in PROCESSING or PENDING status
  useEffect(() => {
    const hasPending = documents.some(
      (d) => d.status === "processing" || d.status === "pending"
    );
    if (!hasPending) return;

    const timer = setInterval(() => {
      loadDocuments(true);
    }, 3000);

    return () => clearInterval(timer);
  }, [documents, loadDocuments]);

  const handleFileUpload = async (files) => {
    if (!files || files.length === 0) return;
    setError("");
    setSuccess("");
    setUploading(true);
    setUploadProgress(`Uploading ${files.length} document(s)...`);

    try {
      const res = await uploadDocuments(files);
      const count = Array.isArray(res) ? res.length : 1;
      setSuccess(`Successfully uploaded ${count} document(s). Processing has started.`);
      await loadDocuments(true);
    } catch (err) {
      setError("Upload failed: " + err.message);
    } finally {
      setUploading(false);
      setUploadProgress("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files);
    }
  };

  const handleDelete = async (doc) => {
    if (!window.confirm(`Are you sure you want to delete "${doc.filename}"? All indexed chunks and embeddings will be removed.`)) {
      return;
    }
    setDeletingId(doc.id);
    setError("");
    try {
      await deleteDocument(doc.id);
      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
      setSuccess(`Document "${doc.filename}" was deleted successfully.`);
    } catch (err) {
      setError("Failed to delete document: " + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return "—";
    const d = new Date(isoStr);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="documents-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Institutional Documents</h1>
          <p className="page-subtitle">
            Upload institutional PDFs, handbooks, guidelines, or policy manuals to ground your AI assistant.
          </p>
        </div>
        <button
          className="btn-secondary"
          onClick={() => loadDocuments()}
          disabled={loading || uploading}
        >
          ↻ Refresh List
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* Upload Drop Zone */}
      <div
        className={`dropzone ${isDragging ? "dropzone-dragover" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.docx"
          onChange={(e) => handleFileUpload(e.target.files)}
          style={{ display: "none" }}
        />
        <div className="dropzone-icon">📥</div>
        <h3 className="dropzone-title">
          {uploading ? uploadProgress : "Drop files here or click to browse"}
        </h3>
        <p className="dropzone-text">
          Supports institutional PDF documents, text guidelines, and policy briefs.
        </p>
        <span className="dropzone-badge">Automatic Chunking & Vector Indexing</span>
      </div>

      {/* Document Library Table */}
      <div className="card documents-table-card">
        <div className="card-header">
          <h2 className="card-title">Indexed Knowledge Base</h2>
          <span className="doc-count">{documents.length} document(s)</span>
        </div>

        {loading ? (
          <div className="table-loader">
            <div className="spinner"></div>
            <p>Loading document registry...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📄</div>
            <h3>No documents uploaded yet</h3>
            <p>Upload a document above to begin indexing and querying your knowledge base.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="documents-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Pages</th>
                  <th>Size</th>
                  <th>Uploaded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td className="doc-name-cell">
                      <span className="file-icon">📄</span>
                      <span className="doc-filename" title={doc.filename}>
                        {doc.filename}
                      </span>
                    </td>
                    <td>
                      <span className={`status-pill status-${doc.status}`}>
                        {doc.status === "processing" && <span className="status-dot-pulse"></span>}
                        {doc.status.toUpperCase()}
                      </span>
                      {doc.error && <p className="status-error-hint">{doc.error}</p>}
                    </td>
                    <td>{doc.page_count ?? "—"}</td>
                    <td>{formatBytes(doc.size_bytes)}</td>
                    <td className="doc-date-cell">{formatDate(doc.created_at)}</td>
                    <td>
                      <button
                        className="btn-danger-outline btn-sm"
                        disabled={deletingId === doc.id}
                        onClick={() => handleDelete(doc)}
                      >
                        {deletingId === doc.id ? "Deleting..." : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
