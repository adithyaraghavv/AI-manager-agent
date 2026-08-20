import { usePhases } from "../hooks/usePhases";

export default function DocTypeSelect({ value, onChange, disabled }) {
  const { phases, error } = usePhases();

  if (error) {
    return (
      <select disabled>
        <option>Couldn't load document types</option>
      </select>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
    >
      <option value="">Select a document type…</option>
      {phases.map((phase) => (
        <optgroup key={phase.name} label={`${phase.sequence}. ${phase.name}`}>
          {phase.required_documents.map((docType) => (
            <option key={docType} value={docType}>
              {docType}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
