import React from 'react';

const SOURCE_STYLES = {
  sap: 'bg-purple-100 text-purple-700 border-purple-200',
  utility: 'bg-teal-100 text-teal-700 border-teal-200',
  travel: 'bg-orange-100 text-orange-700 border-orange-200',
};

const SOURCE_LABELS = {
  sap: 'SAP',
  utility: 'Utility',
  travel: 'Travel',
};

export default function SourceBadge({ source }) {
  const key = (source ?? '').toLowerCase();
  const style = SOURCE_STYLES[key] ?? 'bg-gray-100 text-gray-600 border-gray-200';
  const label = SOURCE_LABELS[key] ?? source;

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${style}`}
    >
      {label}
    </span>
  );
}
