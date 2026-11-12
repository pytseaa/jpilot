import type { Preferences } from "./api";

// These lists must match the ones in backend/app/schemas/search_request.py.
export const EMPLOYMENT_TYPES = ["full-time", "part-time", "contractor"];
export const EXPERIENCE_BANDS = ["0-2", "3-5", "6-9", "10+"];
export const INDUSTRIES = [
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

export const toggleEmploymentType = (value: Preferences, type: string): Preferences => ({
  ...value,
  employment_types: value.employment_types.includes(type)
    ? value.employment_types.filter((t) => t !== type)
    : [...value.employment_types, type],
});

type Props = { value: Preferences; onChange: (next: Preferences) => void };

/** The form's preferences. Region is fixed to Hong Kong, so it is shown and not asked. */
export function PreferenceFields({ value, onChange }: Props) {
  const toggle = (type: string) => onChange(toggleEmploymentType(value, type));

  return (
    <>
      <p className="note">Region: Hong Kong</p>
      <fieldset>
        <legend>Employment type (pick one or more)</legend>
        {EMPLOYMENT_TYPES.map((type) => (
          <label key={type} className="inline">
            <input
              type="checkbox"
              checked={value.employment_types.includes(type)}
              onChange={() => toggle(type)}
            />
            {type}
          </label>
        ))}
      </fieldset>
      <label>
        Experience band (optional)
        <select
          value={value.experience_band ?? ""}
          onChange={(e) => onChange({ ...value, experience_band: e.target.value || null })}
        >
          <option value="">Not specified</option>
          {EXPERIENCE_BANDS.map((band) => (
            <option key={band} value={band}>
              {band} years
            </option>
          ))}
        </select>
      </label>
      <label>
        Industry (optional)
        <select
          value={value.industry ?? ""}
          onChange={(e) => onChange({ ...value, industry: e.target.value || null })}
        >
          <option value="">Not specified</option>
          {INDUSTRIES.map((industry) => (
            <option key={industry} value={industry}>
              {industry}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
