import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCsvProfiles } from "../hooks/useCsvProfiles";
import type { CsvProfile, CsvProfileCreate } from "../lib/api/csvProfiles";
import styles from "./CsvProfileManager.module.css";

type FieldKey = "booking_date" | "amount" | "currency" | "payee" | "purpose" | "external_id";
const FIELD_KEYS: FieldKey[] = [
  "booking_date",
  "amount",
  "currency",
  "payee",
  "purpose",
  "external_id",
];

function emptyForm(): CsvProfileCreate {
  return {
    name: "",
    delimiter: ",",
    date_format: "iso",
    decimal_comma: false,
    column_map: {},
  };
}

function profileToForm(p: CsvProfile): CsvProfileCreate {
  return {
    name: p.name,
    delimiter: p.delimiter,
    date_format: p.date_format,
    decimal_comma: p.decimal_comma,
    column_map: { ...p.column_map },
  };
}

type Props = {
  onClose: () => void;
};

export function CsvProfileManager({ onClose }: Props) {
  const { t } = useTranslation();
  const { profiles, create, update, remove } = useCsvProfiles();

  const [editing, setEditing] = useState<CsvProfile | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<CsvProfileCreate>(emptyForm());

  const isFormOpen = adding || editing !== null;

  function openAdd() {
    setEditing(null);
    setForm(emptyForm());
    setAdding(true);
  }

  function openEdit(p: CsvProfile) {
    setAdding(false);
    setEditing(p);
    setForm(profileToForm(p));
  }

  function closeForm() {
    setAdding(false);
    setEditing(null);
  }

  function setColMap(field: FieldKey, value: string) {
    const aliases = value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setForm((prev) => ({
      ...prev,
      column_map:
        aliases.length > 0
          ? { ...prev.column_map, [field]: aliases }
          : (() => {
              const next = { ...prev.column_map };
              delete next[field];
              return next;
            })(),
    }));
  }

  function handleSave() {
    if (editing) {
      update.mutate({ id: editing.id, data: form }, { onSuccess: closeForm });
    } else {
      create.mutate(form, { onSuccess: closeForm });
    }
  }

  function handleDelete(p: CsvProfile) {
    if (window.confirm(t("csvProfiles.deleteConfirm", { name: p.name }))) {
      remove.mutate(p.id);
    }
  }

  const isSaving = create.isPending || update.isPending;

  return (
    <div className={styles.manager}>
      <div className={styles.header}>
        <h3 className={styles.title}>{t("csvProfiles.title")}</h3>
        <button type="button" className={styles.closeBtn} onClick={onClose}>
          &times;
        </button>
      </div>

      {!isFormOpen && (
        <>
          {profiles.data?.length === 0 && (
            <p className={styles.empty}>{t("csvProfiles.noProfiles")}</p>
          )}
          <ul className={styles.list}>
            {profiles.data?.map((p) => (
              <li key={p.id} className={styles.item}>
                <span className={styles.itemName}>{p.name}</span>
                <span className={styles.itemMeta}>
                  {p.delimiter === "\t" ? t("csvProfiles.delimTab") : p.delimiter} · {p.date_format}
                  {p.decimal_comma ? " · dec," : ""}
                </span>
                <div className={styles.itemActions}>
                  <button type="button" onClick={() => openEdit(p)}>
                    ✎
                  </button>
                  <button type="button" onClick={() => handleDelete(p)}>
                    ✕
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <button type="button" className={styles.addBtn} onClick={openAdd}>
            + {t("csvProfiles.addProfile")}
          </button>
        </>
      )}

      {isFormOpen && (
        <div className={styles.form}>
          <h4 className={styles.formTitle}>
            {editing ? t("csvProfiles.editProfile") : t("csvProfiles.addProfile")}
          </h4>

          <label className={styles.field}>
            <span>{t("csvProfiles.fieldName")}</span>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. DKB Giro"
            />
          </label>

          <div className={styles.row}>
            <label className={styles.field}>
              <span>{t("csvProfiles.fieldDelimiter")}</span>
              <select
                value={form.delimiter}
                onChange={(e) => setForm((f) => ({ ...f, delimiter: e.target.value }))}
              >
                <option value=",">,</option>
                <option value=";">;</option>
                <option value="&#9;">{t("csvProfiles.delimTab")}</option>
              </select>
            </label>

            <label className={styles.field}>
              <span>{t("csvProfiles.fieldDateFormat")}</span>
              <select
                value={form.date_format}
                onChange={(e) => setForm((f) => ({ ...f, date_format: e.target.value }))}
              >
                <option value="iso">{t("csvProfiles.dateFormatIso")}</option>
                <option value="dmy">{t("csvProfiles.dateFormatDmy")}</option>
              </select>
            </label>

            <label className={styles.field}>
              <span>{t("csvProfiles.fieldDecimalComma")}</span>
              <input
                type="checkbox"
                checked={form.decimal_comma}
                onChange={(e) => setForm((f) => ({ ...f, decimal_comma: e.target.checked }))}
              />
            </label>
          </div>

          <details className={styles.colMapSection}>
            <summary>{t("csvProfiles.fieldColumnMap")}</summary>
            <p className={styles.colMapHint}>{t("csvProfiles.columnMapHint")}</p>
            {FIELD_KEYS.map((field) => (
              <label key={field} className={styles.field}>
                <span>
                  {t(
                    `csvProfiles.col${(field.charAt(0).toUpperCase() + field.slice(1)).replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())}` as Parameters<
                      typeof t
                    >[0],
                  )}
                </span>
                <input
                  value={(form.column_map[field] ?? []).join(", ")}
                  onChange={(e) => setColMap(field, e.target.value)}
                  placeholder="leave blank for default"
                />
              </label>
            ))}
          </details>

          <div className={styles.formActions}>
            <button type="button" onClick={closeForm}>
              {t("csvProfiles.cancel")}
            </button>
            <button type="button" onClick={handleSave} disabled={!form.name || isSaving}>
              {t("csvProfiles.save")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
