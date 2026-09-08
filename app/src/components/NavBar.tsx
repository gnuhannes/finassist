import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "./LanguageSwitcher";
import styles from "./NavBar.module.css";

export function NavBar() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();

  // Derived-state pattern: reset drawer on route change during render.
  // useEffect is intentionally avoided here — the project ESLint rule
  // react-hooks/set-state-in-effect disallows calling setState in effects.
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setOpen(false);
  }

  return (
    <nav className={styles.nav}>
      {/* Always-visible top bar (hamburger row) — desktop: hidden */}
      <div className={styles.bar}>
        <span className={styles.brand}>{t("nav.brand")}</span>
        <button
          className={styles.hamburger}
          aria-label={t("nav.menu")}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "✕" : "☰"}
        </button>
      </div>

      {/* Link list — flex-row on desktop, flex-col drawer on mobile */}
      <div className={`${styles.links} ${open ? styles.linksOpen : ""}`}>
        <NavLink to="/" className={({ isActive }) => (isActive ? styles.active : "")} end>
          {t("nav.dashboard")}
        </NavLink>
        <NavLink to="/transactions" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.transactions")}
        </NavLink>
        <NavLink to="/categories" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.categories")}
        </NavLink>
        <NavLink to="/budgets" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.budgets")}
        </NavLink>
        <NavLink to="/recurring" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.recurring")}
        </NavLink>
        <NavLink to="/transfers" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.transfers")}
        </NavLink>
        <NavLink to="/net-worth" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.netWorth")}
        </NavLink>
        <NavLink
          to="/spending-trends"
          className={({ isActive }) => (isActive ? styles.active : "")}
        >
          {t("nav.trends")}
        </NavLink>
        <NavLink to="/annual" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.annual")}
        </NavLink>
        <NavLink to="/rules" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.rules")}
        </NavLink>
        <NavLink to="/import" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.import")}
        </NavLink>
        <NavLink to="/suggestions" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.suggestions")}
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => (isActive ? styles.active : "")}>
          {t("nav.settings")}
        </NavLink>
        <div className={styles.langWrap}>
          <LanguageSwitcher />
        </div>
      </div>
    </nav>
  );
}
