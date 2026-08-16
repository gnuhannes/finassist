import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAccounts } from "../hooks/useAccounts";
import { useImportCsv } from "../hooks/useImportCsv";
import { useCsvProfiles } from "../hooks/useCsvProfiles";
import type { CsvProfile } from "../lib/api/csvProfiles";
import { ApiError } from "../lib/api/client";
import { FileDropZone } from "./FileDropZone";
import { ImportResult } from "./ImportResult";
import { CsvProfileManager } from "./CsvProfileManager";
import styles from "./ImportDialog.module.css";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function ImportDialog({ open, onClose }: Props) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { data: accounts } = useAccounts();
  const { profiles } = useCsvProfiles();
  const mutation = useImportCsv();

  const [accountId, setAccountId] = useState<number | "">("");
  const [selectedProfile, setSelectedProfile] = useState<CsvProfile | null>(null);
  const [delimiter, setDelimiter] = useState(",");
  const [dateFormat, setDateFormat] = useState("iso");
  const [decimalComma, setDecimalComma] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [showProfileManager, setShowProfileManager] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => onClose();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [onClose]);

  function applyProfile(profile: CsvProfile | null) {
    setSelectedProfile(profile);
    if (profile) {
      setDelimiter(profile.delimiter);
      setDateFormat(profile.date_format);
      setDecimalComma(profile.decimal_comma);
    } else {
      setDelimiter(",");
      setDateFormat("iso");
      setDecimalComma(false);
    }
  }

  const resetForm = () => {
    setAccountId("");
    setSelectedProfile(null);
    setDelimiter(",");
    setDateFormat("iso");
    setDecimalComma(false);
    setFile(null);
    setShowProfileManager(false);
    mutation.reset();
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleImportAnother = () => {
    setFile(null);
    mutation.reset();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || accountId === "") return;

    // When a profile is selected, omit format params so the backend uses the profile.
    // The UI shows auto-filled values, but we let the backend be the source of truth.
    // If the user changed a format param from the profile's value, we send it explicitly.
    const delimiterOverride =
      selectedProfile && delimiter === selectedProfile.delimiter ? undefined : delimiter;
    const dateFormatOverride =
      selectedProfile && dateFormat === selectedProfile.date_format ? undefined : dateFormat;
    const decimalCommaOverride =
      selectedProfile && decimalComma === selectedProfile.decimal_comma ? undefined : decimalComma;

    mutation.mutate({
      file,
      accountId: Number(accountId),
      delimiter: delimiterOverride,
      dateFormat: dateFormatOverride,
      decimalComma: decimalCommaOverride,
      profileId: selectedProfile?.id,
    });
  };

  const canSubmit = file !== null && accountId !== "" && !mutation.isPending;

  return (
    <dialog ref={dialogRef} className={styles.dialog}>
      <div className={styles.header}>
        <h2 className={styles.heading}>{t("importDialog.title")}</h2>
        <button type="button" className={styles.closeBtn} onClick={handleClose}>
          &times;
        </button>
      </div>

      {mutation.isSuccess ? (
        <div className={styles.body}>
          <ImportResult
            result={mutation.data}
            importContext={{
              mode: "csv",
              fileName: file?.name,
              accountId: typeof accountId === "number" ? accountId : undefined,
              delimiter,
              dateFormat,
              decimalComma,
            }}
          />
          <div className={styles.actions}>
            <button type="button" onClick={handleImportAnother}>
              {t("importDialog.importAnother")}
            </button>
            <button type="button" onClick={handleClose}>
              {t("importDialog.close")}
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className={styles.body}>
          {/* Profile selector */}
          <div className={styles.profileRow}>
            <label className={styles.field}>
              <span>{t("importDialog.bankProfile")}</span>
              <select
                value={selectedProfile?.id ?? ""}
                onChange={(e) => {
                  const id = e.target.value === "" ? null : Number(e.target.value);
                  applyProfile(profiles.data?.find((p) => p.id === id) ?? null);
                }}
              >
                <option value="">{t("importDialog.bankProfileNone")}</option>
                {profiles.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className={styles.manageProfilesBtn}
              onClick={() => setShowProfileManager((v) => !v)}
            >
              {t("importDialog.manageBankProfiles")}
            </button>
          </div>
          <p className={styles.hint}>{t("importDialog.bankProfileHint")}</p>

          {showProfileManager && <CsvProfileManager onClose={() => setShowProfileManager(false)} />}

          <label className={styles.field}>
            <span>{t("importDialog.account")}</span>
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">{t("importDialog.selectAccount")}</option>
              {accounts?.map((a) => (
                <option key={a.id} value={a.id}>
                  #{a.id} — {a.name} ({a.currency})
                </option>
              ))}
            </select>
          </label>

          <div className={styles.optionsRow}>
            <label className={styles.field}>
              <span>{t("importDialog.delimiter")}</span>
              <select value={delimiter} onChange={(e) => setDelimiter(e.target.value)}>
                <option value=",">,</option>
                <option value=";">;</option>
                <option value="&#9;">{t("importDialog.delimiterTab")}</option>
              </select>
            </label>

            <label className={styles.field}>
              <span>{t("importDialog.dateFormat")}</span>
              <select value={dateFormat} onChange={(e) => setDateFormat(e.target.value)}>
                <option value="iso">{t("importDialog.dateFormatIso")}</option>
                <option value="dmy">{t("importDialog.dateFormatDmy")}</option>
              </select>
            </label>

            <label className={styles.field}>
              <span>{t("importDialog.decimalComma")}</span>
              <input
                type="checkbox"
                checked={decimalComma}
                onChange={(e) => setDecimalComma(e.target.checked)}
              />
            </label>
          </div>

          <FileDropZone onFile={setFile} file={file} accept=".csv" />

          {mutation.isError && (
            <div className={styles.error}>
              {t("importDialog.failedImport", {
                error:
                  mutation.error instanceof ApiError
                    ? ((mutation.error.body as { detail?: string })?.detail ??
                      mutation.error.message)
                    : mutation.error instanceof Error
                      ? mutation.error.message
                      : String(mutation.error),
              })}
            </div>
          )}

          <div className={styles.actions}>
            <button type="button" onClick={handleClose}>
              {t("importDialog.cancel")}
            </button>
            <button type="submit" disabled={!canSubmit}>
              {mutation.isPending ? t("importDialog.importing") : t("importDialog.import")}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}
