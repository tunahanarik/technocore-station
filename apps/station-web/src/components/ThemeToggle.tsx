import { Button } from "@heroui/react";
import { useState } from "react";

import { applyTheme, detectSystemTheme, type Theme } from "../theme";

/**
 * Light/dark switch. The choice is intentionally not persisted: browser
 * storage is banned in this app, so a reload returns to the system theme.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => detectSystemTheme());

  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <Button
      aria-label={next === "dark" ? "Koyu temaya gec" : "Acik temaya gec"}
      onPress={() => {
        applyTheme(next);
        setTheme(next);
      }}
      size="sm"
      variant="secondary"
    >
      <span aria-hidden="true">{next === "dark" ? "◑" : "◐"}</span>
      {next === "dark" ? "Koyu tema" : "Acik tema"}
    </Button>
  );
}
