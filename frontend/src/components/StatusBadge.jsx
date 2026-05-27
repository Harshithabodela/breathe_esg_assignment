import React from 'react';

const STATUS_STYLES = {
  pending: 'bg-gray-100 text-gray-600 border-gray-200',
  flagged: 'bg-amber-100 text-amber-700 border-amber-200',
  approved: 'bg-green-100 text-green-700 border-green-200',
  locked: 'bg-indigo-100 text-indigo-700 border-indigo-200',
};

const STATUS_LABELS = {
  pending: 'Pending',
  flagged: 'Flagged',
  approved: 'Approved',
  locked: 'Locked',
};

export default function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600 border-gray-200';
  const label = STATUS_LABELS[status] ?? status;

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${style}`}
    >
      {label}
    </span>
  );
}
