import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import StatusBadge from './StatusBadge';
import SourceBadge from './SourceBadge';
import { approveRecord, flagRecord, editRecord } from '../api/client';

const TABS = ['Raw Data', 'Normalized', 'Audit Trail'];

function Field({ label, value }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</dt>
      <dd className="text-sm text-gray-900 break-words">{value ?? <span className="text-gray-400 italic">—</span>}</dd>
    </div>
  );
}

export default function RecordDrawer({ record, onClose, onMutated }) {
  const [activeTab, setActiveTab] = useState('Normalized');
  const [flagging, setFlagging] = useState(false);
  const [flagReason, setFlagReason] = useState('');
  const [editing, setEditing] = useState(false);
  const [editCo2e, setEditCo2e] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [approveNote, setApproveNote] = useState('');

  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['records'] });
    queryClient.invalidateQueries({ queryKey: ['summary'] });
    if (onMutated) onMutated();
  };

  const approveMutation = useMutation({
    mutationFn: () => approveRecord(record.id, approveNote),
    onSuccess: invalidate,
  });

  const flagMutation = useMutation({
    mutationFn: () => flagRecord(record.id, flagReason),
    onSuccess: () => {
      setFlagging(false);
      setFlagReason('');
      invalidate();
    },
  });

  const editMutation = useMutation({
    mutationFn: () =>
      editRecord(record.id, {
        co2e_kg: parseFloat(editCo2e),
        description: editDesc,
      }),
    onSuccess: () => {
      setEditing(false);
      invalidate();
    },
  });

  if (!record) return null;

  const isLocked = record.status === 'locked';
  const rawData = record.raw_record_data?.raw_data ?? record.raw_record_data ?? null;
  const auditEvents = record.audit_events ?? [];

  function startEdit() {
    setEditCo2e(String(record.co2e_kg ?? ''));
    setEditDesc(record.description ?? '');
    setEditing(true);
  }

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/30 z-30"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-xl bg-white shadow-xl z-40 flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-gray-200 bg-gray-50">
          <div className="flex flex-col gap-1.5">
            <span className="text-base font-semibold text-gray-900">
              {record.category ?? 'Activity Record'}
            </span>
            <div className="flex items-center gap-2">
              <SourceBadge source={record.source_type} />
              <StatusBadge status={record.status} />
              {isLocked && (
                <span className="text-xs text-indigo-600 font-medium">Read-only</span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="ml-4 text-gray-400 hover:text-gray-600 p-1 rounded focus:outline-none focus:ring-2 focus:ring-gray-300"
            aria-label="Close drawer"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 bg-white">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-emerald-500 text-emerald-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto px-5 py-5">
          {activeTab === 'Raw Data' && (
            <div>
              <p className="text-xs text-gray-500 mb-3">Original as-ingested row data</p>
              {rawData ? (
                <pre className="bg-gray-900 text-green-300 text-xs rounded-lg p-4 overflow-x-auto whitespace-pre-wrap break-words leading-relaxed">
                  {JSON.stringify(rawData, null, 2)}
                </pre>
              ) : (
                <div className="text-sm text-gray-400 italic">No raw data available.</div>
              )}
            </div>
          )}

          {activeTab === 'Normalized' && (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
              <Field label="Period" value={record.period} />
              <Field label="Location" value={record.location_ref} />
              <Field label="Scope" value={record.scope ? `Scope ${record.scope}` : null} />
              <Field label="Category" value={record.category} />
              <Field label="Source Type" value={record.source_type} />
              <Field label="Status" value={record.status} />
              <Field label="Quantity" value={record.quantity != null ? `${record.quantity} ${record.unit ?? ''}`.trim() : null} />
              <Field label="Unit" value={record.unit} />
              <Field
                label="CO2e (kg)"
                value={record.co2e_kg != null ? Number(record.co2e_kg).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : null}
              />
              <Field label="Emission Factor" value={record.emission_factor} />
              <Field label="Emission Factor Source" value={record.emission_factor_source} />
              <div className="col-span-2">
                <Field label="Description" value={record.description} />
              </div>
            </dl>
          )}

          {activeTab === 'Audit Trail' && (
            <div>
              {auditEvents.length === 0 ? (
                <div className="text-sm text-gray-400 italic">No audit events recorded.</div>
              ) : (
                <ol className="relative border-l border-gray-200 ml-3 space-y-4">
                  {auditEvents.map((evt, idx) => (
                    <li key={idx} className="ml-5">
                      <span className="absolute -left-2 flex h-4 w-4 items-center justify-center rounded-full bg-gray-200 ring-4 ring-white">
                        <span className="h-1.5 w-1.5 rounded-full bg-gray-500" />
                      </span>
                      <div className="rounded-md border border-gray-100 bg-gray-50 px-3 py-2.5">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                            {evt.event_type?.replace(/_/g, ' ')}
                          </span>
                          <time className="text-xs text-gray-400">
                            {evt.timestamp
                              ? new Date(evt.timestamp).toLocaleString()
                              : '—'}
                          </time>
                        </div>
                        <div className="text-xs text-gray-600">
                          <span className="font-medium">{evt.actor ?? 'System'}</span>
                          {evt.from_status && evt.to_status && (
                            <span className="ml-1">
                              &mdash;{' '}
                              <span className="text-gray-500">{evt.from_status}</span>
                              {' → '}
                              <span className="text-gray-800">{evt.to_status}</span>
                            </span>
                          )}
                        </div>
                        {evt.note && (
                          <div className="mt-1 text-xs text-gray-500 italic">{evt.note}</div>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </div>

        {/* Action Bar */}
        <div className="border-t border-gray-200 bg-gray-50 px-5 py-4">
          {(approveMutation.isError || flagMutation.isError || editMutation.isError) && (
            <div className="mb-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              An error occurred. Please try again.
            </div>
          )}

          {editing && !isLocked && (
            <div className="mb-3 space-y-2">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">CO2e (kg)</label>
                <input
                  type="number"
                  step="any"
                  value={editCo2e}
                  onChange={(e) => setEditCo2e(e.target.value)}
                  className="w-full rounded border border-gray-300 px-2.5 py-1.5 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                <textarea
                  rows={2}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full rounded border border-gray-300 px-2.5 py-1.5 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 resize-none"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => editMutation.mutate()}
                  disabled={editMutation.isPending}
                  className="flex-1 rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors"
                >
                  {editMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {flagging && !isLocked && (
            <div className="mb-3 space-y-2">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Flag reason</label>
                <textarea
                  rows={2}
                  value={flagReason}
                  onChange={(e) => setFlagReason(e.target.value)}
                  placeholder="Describe why this record is being flagged..."
                  className="w-full rounded border border-gray-300 px-2.5 py-1.5 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 resize-none"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => flagMutation.mutate()}
                  disabled={flagMutation.isPending || !flagReason.trim()}
                  className="flex-1 rounded bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-600 disabled:opacity-60 transition-colors"
                >
                  {flagMutation.isPending ? 'Flagging...' : 'Submit Flag'}
                </button>
                <button
                  onClick={() => { setFlagging(false); setFlagReason(''); }}
                  className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {!editing && !flagging && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => approveMutation.mutate()}
                disabled={isLocked || approveMutation.isPending || record.status === 'approved'}
                className="flex-1 rounded bg-green-600 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {approveMutation.isPending ? 'Approving...' : 'Approve'}
              </button>
              <button
                onClick={() => setFlagging(true)}
                disabled={isLocked}
                className="flex-1 rounded bg-amber-100 border border-amber-300 px-3 py-2 text-sm font-semibold text-amber-700 hover:bg-amber-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Flag
              </button>
              <button
                onClick={startEdit}
                disabled={isLocked}
                className="flex-1 rounded bg-white border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Edit
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
