import type { Preferences } from "./api";

// These lists must match the ones in backend/app/schemas/search_request.py.
const EMPLOYMENT_TYPES = ["full-time", "part-time", "contractor"];
const EXPERIENCE_BANDS = ["0-2", "3-5", "6-9", "10+"];
const INDUSTRIES = [
  "Banking and finance",
  "Insurance",
  "Professional services (accounting, legal, consulting)",
  "Information technology and telecoms",
  "Media, advertising and marketing",
  "Retail and e-commerce",
  "Hospitality, food and tourism",
  "Logistics and transport",
  "Manufacturing and engineering",
  "Construction and property",
  "Healthcare and pharmaceuticals",
  "Education and training",
  "Government and public sector",
  "Non-profit and social services",
  "Energy and utilities",
  "other",
];

export const NO_EMPLOYMENT_TYPE = "Pick at least one employment type.";

type Props = { value: Preferences; onChange: (next: Preferences) => void };

/** Toggle pills for the employment types. The parent supplies the row they sit in. */
export function EmploymentPills({ value, onChange }: Props) {
  const toggle = (type: string) =>
    onChange({
      ...value,
      employment_types: value.employment_types.includes(type)
        ? value.employment_types.filter((t) => t !== type)
        : [...value.employment_types, type],
    });

  return (
    <span className="pills" role="group" aria-label="Employment type (pick one or more)">
      {EMPLOYMENT_TYPES.map((type) => (
        <button
          key={type}
          type="button"
          className="pill"
          aria-pressed={value.employment_types.includes(type)}
          onClick={() => toggle(type)}
        >
          {type}
        </button>
      ))}
    </span>
  );
}

/** Experience band and industry as dropdown pills. Both may stay blank. */
export function BandAndIndustry({ value, onChange }: Props) {
  return (
    <>
      <select
        className="pill-select"
        aria-label="Experience band (optional)"
        value={value.experience_band ?? ""}
        onChange={(e) => onChange({ ...value, experience_band: e.target.value || null })}
      >
        <option value="">Experience band</option>
        {EXPERIENCE_BANDS.map((band) => (
          <option key={band} value={band}>
            {band} years
          </option>
        ))}
      </select>
      <select
        className="pill-select"
        aria-label="Industry (optional)"
        value={value.industry ?? ""}
        onChange={(e) => onChange({ ...value, industry: e.target.value || null })}
      >
        <option value="">Industry</option>
        {INDUSTRIES.map((industry) => (
          <option key={industry} value={industry}>
            {industry}
          </option>
        ))}
      </select>
    </>
  );
}
