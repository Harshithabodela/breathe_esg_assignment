import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../App';
import {
  getActivityRecords,
  getActivitySummary,
  approveRecord,
  bulkApprove,
  logout,
} from '../api/client';
import StatusBadge from '../components/StatusBadge';
import SourceBadge from '../components/SourceBadge';
import RecordDrawer from '../components/RecordDrawer';

function SummaryCard({ label, value, colorClass }) {
  return (
    <div className={`bg-white rounded-lg border px-5 py-4 flex flex-col gap-1 ${colorClass ?? 'border-gray-200'}`}>
      <span className="text-2xl font-bold text-gray-900 tabular-nums">
        {value ?? <span className="text-gray-300">—</span>}
      </span>
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
    </div>
  );
}

const SOURCE_OPTIONS = ['all', 'sap', 'utility', 'travel'];
const SCOPE_OPTIONS = ['all', '1', '2', '3'];
const STATUS_OPTIONS = ['all', 'pending', 'flagged', 'approved', 'locked'];

export default function DashboardPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [filters, setFilters] = useState({
    source_type: 'all',
    scope: 'all',
    status: 'all',
    date_from: '',
    date_to: '',
  });

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [drawerRecord, setDrawerRecord] = useState(null);

  const queryParams = {};
  if (filters.source_type !== 'all') queryParams.source_type = filters.source_type;
  if (filters.scope !== 'all') queryParams.scope = filters.scope;
  if (filters.status !== 'all') queryParams.review_status = filters.status;
  if (filters.date_from) queryParams.date_from = filters.date_from;
  if (filters.date_to) queryParams.date_to = filters.date_to;

  const { data: recordsData, isLoading: recordsLoading } = useQuery({
    queryKey: ['records', queryParams],
    queryFn: () => getActivityRecords(queryParams).then((r) => r.data),
  });

  const { data: summaryData } = useQuery({
    queryKey: ['summary'],
    queryFn: () => getActivitySummary().then((r) => r.data),
  });

  const bulkApproveMutation = useMutation({
    mutationFn: () => bulkApprove(Array.from(selectedIds)),
    onSuccess: () => {
      setSelectedIds(new Set());
      queryClient.invalidateQueries({ queryKey: ['records'] });
      queryClient.invalidateQueries({ queryKey: ['summary'] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: (id) => approveRecord(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['records'] });
      queryClient.invalidateQueries({ queryKey: ['summary'] });
    },
  });

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setUser(null);
      navigate('/login', { replace: true });
    }
  }

  function updateFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setSelectedIds(new Set());
  }

  const records = Array.isArray(recordsData)
    ? recordsData
    : recordsData?.results ?? [];

  const summary = summaryData ?? {};

  function toggleSelectAll(e) {
    if (e.target.checked) {
      const approvableIds = records
        .filter((r) => r.review_status !== "locked" && r.review_status !== "approved")
        .map((r) => r.id);
      setSelectedIds(new Set(approvableIds));
    } else {
      setSelectedIds(new Set());
    }
  }

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const totalCo2e =
    summary.total_co2e_kg != null
      ? (summary.total_co2e_kg / 1000).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : '—';

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
            className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-emerald-700 bg-emerald-50"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            Dashboard
          </Link>
          <Link
            to="/ingest"
            className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
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

      {/* Main content */}
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <h1 className="text-lg font-semibold text-gray-900">Emissions Review Dashboard</h1>
          <p className="text-xs text-gray-500 mt-0.5">Review, approve, and manage activity records</p>
        </header>

        <div className="flex-1 px-6 py-5 space-y-5 overflow-auto">
          {/* Summary Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <SummaryCard label="Total Records" value={summary.total} />
            <SummaryCard label="Pending" value={summary.by_status?.pending} />
            <SummaryCard
              label="Flagged"
              value={summary.by_status?.flagged}
              colorClass="border-amber-200 bg-amber-50"
            />
            <SummaryCard
              label="Approved"
              value={summary.by_status?.approved}
              colorClass="border-green-200 bg-green-50"
            />
            <SummaryCard label="Locked" value={summary.by_status?.locked} />
            <SummaryCard
              label="Total CO2e (t)"
              value={totalCo2e}
            />
          </div>

          {/* Filters */}
          <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Source Type</label>
              <select
                value={filters.source_type}
                onChange={(e) => updateFilter('source_type', e.target.value)}
                className="rounded border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {SOURCE_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o === 'all' ? 'All Sources' : o.charAt(0).toUpperCase() + o.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Scope</label>
              <select
                value={filters.scope}
                onChange={(e) => updateFilter('scope', e.target.value)}
                className="rounded border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {SCOPE_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o === 'all' ? 'All Scopes' : `Scope ${o}`}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Status</label>
              <select
                value={filters.status}
                onChange={(e) => updateFilter('status', e.target.value)}
                className="rounded border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {STATUS_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o === 'all' ? 'All Statuses' : o.charAt(0).toUpperCase() + o.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Period From</label>
              <input
                type="date"
                value={filters.date_from}
                onChange={(e) => updateFilter('date_from', e.target.value)}
                className="rounded border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Period To</label>
              <input
                type="date"
                value={filters.date_to}
                onChange={(e) => updateFilter('date_to', e.target.value)}
                className="rounded border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <button
              onClick={() =>
                setFilters({ source_type: 'all', scope: 'all', status: 'all', date_from: '', date_to: '' })
              }
              className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 transition-colors self-end"
            >
              Clear
            </button>
          </div>

          {/* Bulk Actions */}
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2.5">
              <span className="text-sm font-medium text-emerald-700">
                {selectedIds.size} record{selectedIds.size !== 1 ? 's' : ''} selected
              </span>
              <button
                onClick={() => bulkApproveMutation.mutate()}
                disabled={bulkApproveMutation.isPending}
                className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors"
              >
                {bulkApproveMutation.isPending ? 'Approving...' : 'Bulk Approve'}
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                Clear selection
              </button>
            </div>
          )}

          {/* Records Table */}
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            {recordsLoading ? (
              <div className="flex items-center justify-center py-16 text-sm text-gray-400">
                Loading records...
              </div>
            ) : records.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <svg className="w-8 h-8 mb-2 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="text-sm">No records match the current filters.</span>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="pl-4 pr-2 py-3 w-10">
                        <input
                          type="checkbox"
                          className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                          checked={
                            selectedIds.size > 0 &&
                            records
                              .filter((r) => r.review_status !== "locked" && r.review_status !== "approved")
                              .every((r) => selectedIds.has(r.id))
                          }
                          onChange={toggleSelectAll}
                        />
                      </th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Source</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Scope</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Category</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Period</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Location</th>
                      <th className="px-3 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">CO2e (kg)</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                      <th className="px-3 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {records.map((record) => {
                      const isLocked = record.review_status === 'locked';
                      const isApproved = record.review_status === 'approved';
                      const isSelectable = !isLocked && !isApproved;
                      return (
                        <tr
                          key={record.id}
                          className="hover:bg-gray-50 cursor-pointer transition-colors"
                          onClick={() => setDrawerRecord(record)}
                        >
                          <td
                            className="pl-4 pr-2 py-3"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              type="checkbox"
                              className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500 disabled:opacity-40"
                              disabled={!isSelectable}
                              checked={selectedIds.has(record.id)}
                              onChange={() => toggleSelect(record.id)}
                            />
                          </td>
                          <td className="px-3 py-3">
                            <SourceBadge source={record.source_type} />
                          </td>
                          <td className="px-3 py-3 text-sm text-gray-700">
                            {record.scope ? `Scope ${record.scope}` : <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-3 py-3 text-sm text-gray-700 max-w-[180px] truncate">
                            {record.category ?? <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-3 py-3 text-sm text-gray-700">
                            {`${record.period_start} – ${record.period_end}` ?? <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-3 py-3 text-sm text-gray-700 max-w-[140px] truncate">
                            {record.location_ref ?? <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-3 py-3 text-sm text-gray-900 text-right tabular-nums">
                            {record.co2e_kg != null
                              ? Number(record.co2e_kg).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                              : <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-3 py-3">
                            <StatusBadge status={record.review_status} />
                          </td>
                          <td
                            className="px-3 py-3 text-right whitespace-nowrap"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              disabled={isLocked || isApproved || approveMutation.isPending}
                              onClick={() => approveMutation.mutate(record.id)}
                              className="inline-flex items-center rounded px-2.5 py-1 text-xs font-semibold text-white bg-green-600 hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors mr-1"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => setDrawerRecord(record)}
                              className="inline-flex items-center rounded px-2.5 py-1 text-xs font-semibold text-amber-700 bg-amber-100 hover:bg-amber-200 transition-colors"
                            >
                              Flag
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Record Drawer */}
      {drawerRecord && (
        <RecordDrawer
          record={drawerRecord}
          onClose={() => setDrawerRecord(null)}
          onMutated={() => setDrawerRecord(null)}
        />
      )}
    </div>
  );
}
