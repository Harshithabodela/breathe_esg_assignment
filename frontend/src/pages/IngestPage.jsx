import React, { useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../App';
import { uploadFile, getIngestions, logout } from '../api/client';
import SourceBadge from '../components/SourceBadge';

const SOURCE_TYPES = [
  {
    key: 'sap',
    label: 'SAP',
    description: 'ERP system exports — purchase orders, energy usage, fuel consumption logs.',
    accept: '.txt,.csv,.xlsx',
  },
  {
    key: 'utility',
    label: 'Utility Bills',
    description: 'Electricity, gas, and water utility meter data and invoice exports.',
    accept: '.txt,.csv,.xlsx',
  },
  {
    key: 'travel',
    label: 'Travel & Expense',
    description: 'Business travel records including flights, rail, and accommodation data.',
    accept: '.txt,.csv,.xlsx',
  },
];

function UploadZone({ source }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: () => uploadFile(file, source.key),
    onSuccess: (res) => {
      setResult(res.data);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      queryClient.invalidateQueries({ queryKey: ['ingestions'] });
    },
    onError: (err) => {
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        'Upload failed. Please check your file and try again.';
      setResult({ error: detail });
    },
  });

  function handleFileChange(e) {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setResult(null);
  }

  function handleUpload() {
    if (!file) return;
    setResult(null);
    uploadMutation.mutate();
  }

  const colorMap = {
    sap: 'border-purple-200 bg-purple-50',
    utility: 'border-teal-200 bg-teal-50',
    travel: 'border-orange-200 bg-orange-50',
  };

  const borderActive = colorMap[source.key] ?? 'border-gray-200 bg-gray-50';

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className={`px-5 py-4 border-b border-gray-100 ${borderActive}`}>
        <div className="flex items-center gap-2 mb-1">
          <SourceBadge source={source.key} />
          <span className="text-sm font-semibold text-gray-800">{source.label}</span>
        </div>
        <p className="text-xs text-gray-500">{source.description}</p>
      </div>

      <div className="px-5 py-4 space-y-3">
        <div className="flex items-center gap-3">
          <label className="flex-1">
            <span className="sr-only">Choose file for {source.label}</span>
            <input
              ref={fileInputRef}
              type="file"
              accept={source.accept}
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 cursor-pointer"
            />
          </label>
          <button
            onClick={handleUpload}
            disabled={!file || uploadMutation.isPending}
            className="shrink-0 rounded bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {uploadMutation.isPending ? 'Uploading...' : 'Upload'}
          </button>
        </div>

        {file && !uploadMutation.isPending && !result && (
          <p className="text-xs text-gray-400">
            Ready to upload: <span className="font-medium text-gray-600">{file.name}</span>
          </p>
        )}

        {result && (
          <div
            className={`rounded-md border p-3 text-sm ${
              result.error
                ? 'bg-red-50 border-red-200 text-red-700'
                : 'bg-green-50 border-green-200 text-green-800'
            }`}
          >
            {result.error ? (
              <p className="font-medium">{result.error}</p>
            ) : (
              <div className="space-y-1.5">
                <div className="flex items-center gap-4">
                  <span>
                    <span className="font-semibold">{result.rows_ok ?? 0}</span> rows ingested
                  </span>
                  {result.rows_error > 0 && (
                    <span className="text-amber-700">
                      <span className="font-semibold">{result.rows_error}</span> errors
                    </span>
                  )}
                </div>
                {Array.isArray(result.errors) && result.errors.length > 0 && (
                  <div className="mt-2 border-t border-green-200 pt-2">
                    <p className="text-xs font-medium text-gray-600 mb-1">Error details:</p>
                    <ul className="list-disc list-inside space-y-0.5">
                      {result.errors.map((err, i) => (
                        <li key={i} className="text-xs text-amber-700">
                          {typeof err === 'string' ? err : JSON.stringify(err)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const styles = {
    success: 'bg-green-100 text-green-700 border-green-200',
    error: 'bg-red-100 text-red-700 border-red-200',
    partial: 'bg-amber-100 text-amber-700 border-amber-200',
    processing: 'bg-blue-100 text-blue-700 border-blue-200',
  };
  const style = styles[status] ?? 'bg-gray-100 text-gray-600 border-gray-200';
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status ?? '—'}
    </span>
  );
}

export default function IngestPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const { data: ingestionsData, isLoading } = useQuery({
    queryKey: ['ingestions'],
    queryFn: () => getIngestions().then((r) => r.data),
  });

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setUser(null);
      navigate('/login', { replace: true });
    }
  }

  const ingestions = Array.isArray(ingestionsData)
    ? ingestionsData
    : ingestionsData?.results ?? [];

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-100">
          <span className="text-base font-bold text-gray-900 tracking-tight">Breathe ESG</span>
          <p className="text-xs text-gray-400 mt-0.5">Review Platform</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          <Link
            to="/dashboard"
            className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            Dashboard
          </Link>
          <Link
            to="/ingest"
            className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-emerald-700 bg-emerald-50"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Ingest Data
          </Link>
        </nav>
        <div className="px-4 py-4 border-t border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-700">{user?.username ?? user?.email ?? 'Analyst'}</p>
              <p className="text-xs text-gray-400">{user?.email ?? ''}</p>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="text-gray-400 hover:text-gray-600 p-1 rounded"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <h1 className="text-lg font-semibold text-gray-900">Ingest Data</h1>
          <p className="text-xs text-gray-500 mt-0.5">Upload source files to import emissions data</p>
        </header>

        <div className="flex-1 px-6 py-5 space-y-6 overflow-auto">
          {/* Upload Zones */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Upload Files</h2>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {SOURCE_TYPES.map((source) => (
                <UploadZone key={source.key} source={source} />
              ))}
            </div>
          </div>

          {/* Ingestion History */}
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Ingestion History</h2>
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              {isLoading ? (
                <div className="flex items-center justify-center py-12 text-sm text-gray-400">
                  Loading history...
                </div>
              ) : ingestions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                  <svg className="w-8 h-8 mb-2 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="text-sm">No ingestion records yet.</span>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Filename</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Source</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Date</th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Rows OK</th>
                        <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Rows Error</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 bg-white">
                      {ingestions.map((ing) => (
                        <tr key={ing.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-sm text-gray-900 font-medium max-w-[220px] truncate">
                            {ing.filename ?? ing.file_name ?? '—'}
                          </td>
                          <td className="px-4 py-3">
                            <SourceBadge source={ing.source_type} />
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {ing.created_at || ing.uploaded_at
                              ? new Date(ing.created_at ?? ing.uploaded_at).toLocaleString()
                              : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill status={ing.status} />
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900 text-right tabular-nums">
                            {ing.rows_ok ?? '—'}
                          </td>
                          <td className="px-4 py-3 text-sm text-right tabular-nums">
                            <span className={ing.rows_error > 0 ? 'text-amber-600 font-medium' : 'text-gray-500'}>
                              {ing.rows_error ?? '—'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
