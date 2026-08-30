import { Alert, Button, Checkbox, Input, Label, Modal, TextField } from "@heroui/react";
import { useEffect, useId, useRef, useState } from "react";

import {
  adoptRecovery,
  createIdentity,
  exportRecovery,
  fetchIdentity,
  inspectRecovery,
  revokeIdentity,
  verifyRecovery,
} from "../../api/client";
import type { IdentityStatus, ProtectionMode, RecoveryInspectResult } from "../../api/types";
import { StatusPill } from "../StatusPill";

/**
 * Every dialog in this file follows the same two rules:
 *
 * 1. Passphrases live in local component state only. They are wiped whenever
 *    the dialog closes or the operation finishes, and they are never lifted
 *    into a store, a context or browser storage.
 * 2. There is no seed anywhere - no field that accepts one, and no field that
 *    displays one.
 */

interface DialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onUpdated: (status: IdentityStatus) => void;
  readonly status: IdentityStatus;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Islem tamamlanamadi.";
}

/** A labelled passphrase input. Never bound to a saved-password autofill. */
function PassphraseField({
  label,
  value,
  onChange,
  autoComplete,
  describedBy,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (next: string) => void;
  readonly autoComplete: "new-password" | "current-password";
  readonly describedBy?: string;
}) {
  return (
    <TextField className="w-full" onChange={onChange} type="password" value={value}>
      <Label>{label}</Label>
      <Input aria-describedby={describedBy} autoComplete={autoComplete} variant="secondary" />
    </TextField>
  );
}

/** Shared shell so every dialog gets the same focus and dismissal behaviour. */
function DialogShell({
  isOpen,
  onClose,
  title,
  children,
  footer,
}: {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly title: string;
  readonly children: React.ReactNode;
  readonly footer: React.ReactNode;
}) {
  return (
    <Modal>
      <Modal.Backdrop
        isOpen={isOpen}
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
      >
        <Modal.Container size="lg">
          <Modal.Dialog aria-label={title}>
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Heading>{title}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="flex flex-col gap-4">{children}</Modal.Body>
            <Modal.Footer className="gap-2">{footer}</Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </Modal>
  );
}

function ErrorAlert({ title, message }: { readonly title: string; readonly message: string }) {
  return (
    <Alert status="danger">
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Title>{title}</Alert.Title>
        <Alert.Description>{message}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

// --- create ---------------------------------------------------------------


/**
 * An accessible picker for a `.tcrec` recovery file.
 *
 * A bare `<input type="file">` renders as an unstyled, browser-specific
 * control with no visible boundary and no indication of what belongs in it.
 * It is also easy to miss entirely inside a dialog. This wraps one in a
 * labelled dropzone with an explicit button.
 *
 * The native input is kept - it is the only thing that can open the OS file
 * dialog - but it is taken out of the tab order and driven by the button, so
 * keyboard users get one predictable stop with a real accessible name rather
 * than two controls that do the same thing.
 *
 * Only the file's *name* ever reaches the DOM. Its contents are read by the
 * browser when the form is submitted and are never placed in markup, state or
 * a log line.
 */
function RecoveryFileField({
  file,
  isDisabled = false,
  onSelect,
  errorMessage,
}: {
  readonly file: File | null;
  readonly isDisabled?: boolean;
  readonly onSelect: (file: File | null) => void;
  readonly errorMessage?: string | null;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const id = useId();
  const describedBy = `${id}-hint${errorMessage != null ? ` ${id}-error` : ""}`;

  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm font-medium" id={`${id}-label`}>
        Recovery dosyasi (.tcrec)
      </span>

      <div
        className={[
          "flex flex-col gap-2 rounded-lg border border-dashed p-4 transition-colors",
          "border-border hover:border-accent",
          "focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/40",
          isDisabled ? "opacity-60" : "",
        ].join(" ")}
        data-selected={file !== null}
        data-testid="recovery-dropzone"
      >
        {file === null ? (
          <p className="text-xs text-muted" id={`${id}-hint`}>
            Henuz dosya secilmedi. Daha once disa aktardiginiz{" "}
            <code className="font-mono">.tcrec</code> dosyasini secin.
          </p>
        ) : (
          <p className="flex flex-wrap items-center gap-2 text-xs" id={`${id}-hint`}>
            <StatusPill label="Secildi" tone="ok" />
            <span className="font-mono break-all text-foreground">{file.name}</span>
          </p>
        )}

        <div>
          <Button
            aria-describedby={describedBy}
            aria-labelledby={`${id}-label`}
            isDisabled={isDisabled}
            onPress={() => inputRef.current?.click()}
            size="sm"
            variant="secondary"
          >
            {file === null ? "Dosya sec" : "Baska dosya sec"}
          </Button>
        </div>

        {/* Visually hidden and out of the tab order: the button above is the
            single, named control. `sr-only` rather than `display:none`,
            because a hidden input cannot be activated in some browsers. */}
        <input
          accept=".tcrec,application/octet-stream"
          aria-hidden="true"
          className="sr-only"
          disabled={isDisabled}
          onChange={(event) => onSelect(event.target.files?.[0] ?? null)}
          ref={inputRef}
          tabIndex={-1}
          type="file"
        />
      </div>

      {errorMessage != null && (
        <p className="text-xs text-danger" id={`${id}-error`}>
          {errorMessage}
        </p>
      )}
    </div>
  );
}

export function CreateIdentityDialog({ isOpen, onClose, onUpdated, status }: DialogProps) {
  const [protection, setProtection] = useState<ProtectionMode>(status.default_protection);
  const [passphrase, setPassphrase] = useState("");
  const [confirmPassphrase, setConfirmPassphrase] = useState("");
  const [acceptRisk, setAcceptRisk] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Wipe every secret-bearing field whenever the dialog is not on screen.
  useEffect(() => {
    if (!isOpen) {
      setPassphrase("");
      setConfirmPassphrase("");
      setConfirmation("");
      setAcceptRisk(false);
      setError(null);
      setProtection(status.default_protection);
    }
  }, [isOpen, status.default_protection]);

  const usesPassphrase = protection === "dpapi+passphrase";
  const tooShort = usesPassphrase && passphrase.length < status.min_passphrase_chars;
  const mismatch = usesPassphrase && passphrase !== confirmPassphrase;
  const canSubmit =
    !busy &&
    confirmation === status.create_confirmation_text &&
    (usesPassphrase ? !tooShort && !mismatch : acceptRisk);

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const next = await createIdentity({
        protection,
        passphrase: usesPassphrase ? passphrase : null,
        passphraseConfirm: usesPassphrase ? confirmPassphrase : null,
        label: "",
        confirmation,
        acceptDpapiOnlyRisk: !usesPassphrase && acceptRisk,
      });
      setPassphrase("");
      setConfirmPassphrase("");
      onUpdated(next);
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogShell
      footer={
        <>
          <Button isDisabled={busy} onPress={onClose} variant="secondary">
            Vazgec
          </Button>
          <Button isDisabled={!canSubmit} onPress={() => void submit()}>
            {busy ? "Olusturuluyor..." : "Kimligi olustur"}
          </Button>
        </>
      }
      isOpen={isOpen}
      onClose={onClose}
      title="Yeni kimlik olustur"
    >
      <Alert status="default">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Bu bir cuzdan adresi degildir</Alert.Title>
          <Alert.Description>
            Ed25519 did:key yalnizca bir anahtar sahipligi gostergesidir. Gercek
            kimliginizi, dogrulugu, token sahipligini veya bir airdrop hakkini
            kanitlamaz.
          </Alert.Description>
        </Alert.Content>
      </Alert>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-foreground">Koruma bicimi</legend>

        <label className="flex items-start gap-2 rounded-lg border border-border p-3">
          <input
            checked={protection === "dpapi+passphrase"}
            name="protection"
            onChange={() => setProtection("dpapi+passphrase")}
            type="radio"
            value="dpapi+passphrase"
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-sm font-medium">DPAPI + parola (onerilen)</span>
            <span className="text-xs text-muted">
              Seed once parolanizdan turetilen anahtarla sifrelenir, sonra Windows
              DPAPI ile korunur. Bu Windows kullanicisi olarak calisan bir
              saldirgan bile parolayi bilmeden seed&apos;e ulasamaz.
            </span>
          </span>
        </label>

        <label className="flex items-start gap-2 rounded-lg border border-border p-3">
          <input
            checked={protection === "dpapi"}
            name="protection"
            onChange={() => setProtection("dpapi")}
            type="radio"
            value="dpapi"
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-sm font-medium">Yalniz DPAPI</span>
            <span className="text-xs text-muted">
              Parola sorulmaz. Bu Windows kullanicisi olarak calisan herhangi bir
              program seed&apos;i acabilir.
            </span>
          </span>
        </label>
      </fieldset>

      {usesPassphrase ? (
        <div className="flex flex-col gap-3">
          <PassphraseField
            autoComplete="new-password"
            describedBy="passphrase-rule"
            label="Kasa parolasi"
            onChange={setPassphrase}
            value={passphrase}
          />
          <p className="text-xs text-muted" id="passphrase-rule">
            En az {status.min_passphrase_chars} karakter. Uzunluk disinda bir
            kural yoktur; uzun bir cumle kisa bir sifreden iyidir.
          </p>
          <PassphraseField
            autoComplete="new-password"
            label="Kasa parolasi (tekrar)"
            onChange={setConfirmPassphrase}
            value={confirmPassphrase}
          />
          {tooShort && passphrase.length > 0 && (
            <p className="text-xs text-danger">
              Parola en az {status.min_passphrase_chars} karakter olmalidir.
            </p>
          )}
          {mismatch && confirmPassphrase.length > 0 && (
            <p className="text-xs text-danger">Parolalar eslesmiyor.</p>
          )}
        </div>
      ) : (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Parolasiz koruma riski</Alert.Title>
            <Alert.Description>
              <Checkbox isSelected={acceptRisk} onChange={setAcceptRisk}>
                <Checkbox.Content>
                  <Checkbox.Control>
                    <Checkbox.Indicator />
                  </Checkbox.Control>
                  Bu riski anliyorum ve parolasiz devam etmek istiyorum.
                </Checkbox.Content>
              </Checkbox>
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <TextField className="w-full" onChange={setConfirmation} value={confirmation}>
        <Label>
          Onaylamak icin tam olarak &quot;{status.create_confirmation_text}&quot; yazin
        </Label>
        <Input autoComplete="off" variant="secondary" />
      </TextField>

      {error !== null && <ErrorAlert message={error} title="Kimlik olusturulamadi" />}
    </DialogShell>
  );
}

// --- recovery export -------------------------------------------------------

export function ExportRecoveryDialog({ isOpen, onClose, onUpdated, status }: DialogProps) {
  const [recoveryPassphrase, setRecoveryPassphrase] = useState("");
  const [confirmPassphrase, setConfirmPassphrase] = useState("");
  const [vaultPassphrase, setVaultPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setRecoveryPassphrase("");
      setConfirmPassphrase("");
      setVaultPassphrase("");
      setError(null);
      setDone(false);
    }
  }, [isOpen]);

  const needsVaultPassphrase = status.identity?.protection === "dpapi+passphrase";
  const tooShort = recoveryPassphrase.length < status.min_passphrase_chars;
  const mismatch = recoveryPassphrase !== confirmPassphrase;

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename } = await exportRecovery({
        recoveryPassphrase,
        recoveryPassphraseConfirm: confirmPassphrase,
        vaultPassphrase: needsVaultPassphrase ? vaultPassphrase : null,
      });

      // Hand the ciphertext to the browser, then drop it immediately.
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);

      setRecoveryPassphrase("");
      setConfirmPassphrase("");
      setVaultPassphrase("");
      setDone(true);
      onUpdated(await fetchIdentity());
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogShell
      footer={
        <>
          <Button isDisabled={busy} onPress={onClose} variant="secondary">
            {done ? "Kapat" : "Vazgec"}
          </Button>
          <Button isDisabled={busy || tooShort || mismatch} onPress={() => void submit()}>
            {busy ? "Hazirlaniyor..." : "Recovery dosyasini indir"}
          </Button>
        </>
      }
      isOpen={isOpen}
      onClose={onClose}
      title="Recovery dosyasi olustur"
    >
      <Alert status="warning">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Iki bagimsiz kopya hazirlayin</Alert.Title>
          <Alert.Description>
            Recovery dosyasinin guvenligi tamamen sectiginiz parolaya baglidir.
            Dosyayi ve parolayi ayri yerlerde saklayin, en az iki bagimsiz
            cevrimdisi kopya alin. Parola kaybolursa kimlik geri getirilemez.
          </Alert.Description>
        </Alert.Content>
      </Alert>

      <PassphraseField
        autoComplete="new-password"
        label="Recovery parolasi"
        onChange={setRecoveryPassphrase}
        value={recoveryPassphrase}
      />
      <PassphraseField
        autoComplete="new-password"
        label="Recovery parolasi (tekrar)"
        onChange={setConfirmPassphrase}
        value={confirmPassphrase}
      />
      <p className="text-xs text-muted">
        Bu parola kasa parolasindan ayridir ve hicbir yerde saklanmaz.
      </p>

      {needsVaultPassphrase && (
        <PassphraseField
          autoComplete="current-password"
          label="Kasa parolasi (secret'i acmak icin)"
          onChange={setVaultPassphrase}
          value={vaultPassphrase}
        />
      )}

      {done && (
        <Alert status="success">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Dosya indirildi</Alert.Title>
            <Alert.Description>
              Simdi restore-test yapin. Test tamamlanmadan kimlik hazir sayilmaz.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {error !== null && <ErrorAlert message={error} title="Recovery olusturulamadi" />}
    </DialogShell>
  );
}

// --- restore test ----------------------------------------------------------

export function RestoreTestDialog({ isOpen, onClose, onUpdated }: DialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setPassphrase("");
      setError(null);
    }
  }, [isOpen]);

  async function submit(): Promise<void> {
    if (file === null) return;
    setBusy(true);
    setError(null);
    try {
      const next = await verifyRecovery(file, passphrase);
      setPassphrase("");
      onUpdated(next);
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogShell
      footer={
        <>
          <Button isDisabled={busy} onPress={onClose} variant="secondary">
            Vazgec
          </Button>
          <Button isDisabled={busy || file === null} onPress={() => void submit()}>
            {busy ? "Dogrulaniyor..." : "Restore-test yap"}
          </Button>
        </>
      }
      isOpen={isOpen}
      onClose={onClose}
      title="Restore-test"
    >
      <p className="text-sm text-muted">
        Recovery dosyaniz gercekten bu kimligi geri getiriyor mu? Test dosyadan
        secret&apos;i cozer, DID&apos;i yeniden turetir ve kurulu kimlikle
        karsilastirir. Kasaya dokunmaz ve basarisiz olursa hicbir sey degismez.
      </p>

      <RecoveryFileField
        errorMessage={file === null && error !== null ? "Once bir dosya secin." : null}
        file={file}
        onSelect={setFile}
      />

      <PassphraseField
        autoComplete="current-password"
        label="Recovery parolasi"
        onChange={setPassphrase}
        value={passphrase}
      />

      {error !== null && <ErrorAlert message={error} title="Restore-test basarisiz" />}
    </DialogShell>
  );
}

// --- clean profile adoption ------------------------------------------------

export function AdoptRecoveryDialog({ isOpen, onClose, onUpdated, status }: DialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [recoveryPassphrase, setRecoveryPassphrase] = useState("");
  const [inspected, setInspected] = useState<RecoveryInspectResult | null>(null);
  const [protection, setProtection] = useState<ProtectionMode>(status.default_protection);
  const [vaultPassphrase, setVaultPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setRecoveryPassphrase("");
      setVaultPassphrase("");
      setInspected(null);
      setError(null);
      setProtection(status.default_protection);
    }
  }, [isOpen, status.default_protection]);

  async function inspect(): Promise<void> {
    if (file === null) return;
    setBusy(true);
    setError(null);
    try {
      setInspected(await inspectRecovery(file, recoveryPassphrase));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function adopt(): Promise<void> {
    if (file === null || inspected === null) return;
    setBusy(true);
    setError(null);
    try {
      const next = await adoptRecovery({
        file,
        recoveryPassphrase,
        protection,
        vaultPassphrase: protection === "dpapi+passphrase" ? vaultPassphrase : null,
        confirmDid: inspected.did,
        label: "",
      });
      setRecoveryPassphrase("");
      setVaultPassphrase("");
      onUpdated(next);
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogShell
      footer={
        <>
          <Button isDisabled={busy} onPress={onClose} variant="secondary">
            Vazgec
          </Button>
          {inspected === null ? (
            <Button isDisabled={busy || file === null} onPress={() => void inspect()}>
              {busy ? "Aciliyor..." : "Dosyayi kontrol et"}
            </Button>
          ) : (
            <Button isDisabled={busy} onPress={() => void adopt()}>
              {busy ? "Kuruluyor..." : "Bu kimligi kur"}
            </Button>
          )}
        </>
      }
      isOpen={isOpen}
      onClose={onClose}
      title="Recovery dosyasindan kimlik kur"
    >
      <p className="text-sm text-muted">
        Bos bir profilde, yalnizca recovery dosyasi ve parolasi ile kimliginizi
        geri getirebilirsiniz. Eski bilgisayarin DPAPI kasasina veya eski Windows
        hesabina ihtiyac yoktur.
      </p>

      <RecoveryFileField
        file={file}
        isDisabled={inspected !== null}
        onSelect={setFile}
      />

      {inspected === null ? (
        <PassphraseField
          autoComplete="current-password"
          label="Recovery parolasi"
          onChange={setRecoveryPassphrase}
          value={recoveryPassphrase}
        />
      ) : (
        <>
          <Alert status="accent">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Bu kimligi kurmak uzeresiniz</Alert.Title>
              <Alert.Description>
                <span className="block font-mono text-xs break-all">{inspected.did}</span>
                <span className="mt-1 block text-xs">
                  Fingerprint: {inspected.fingerprint_short}
                </span>
              </Alert.Description>
            </Alert.Content>
          </Alert>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-foreground">
              Bu bilgisayardaki koruma bicimi
            </legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                checked={protection === "dpapi+passphrase"}
                name="adopt-protection"
                onChange={() => setProtection("dpapi+passphrase")}
                type="radio"
              />
              DPAPI + parola (onerilen)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                checked={protection === "dpapi"}
                name="adopt-protection"
                onChange={() => setProtection("dpapi")}
                type="radio"
              />
              Yalniz DPAPI
            </label>
          </fieldset>

          {protection === "dpapi+passphrase" && (
            <PassphraseField
              autoComplete="new-password"
              label="Yeni kasa parolasi"
              onChange={setVaultPassphrase}
              value={vaultPassphrase}
            />
          )}
        </>
      )}

      {error !== null && <ErrorAlert message={error} title="Kimlik kurulamadi" />}
    </DialogShell>
  );
}

// --- revoke ----------------------------------------------------------------

export function RevokeIdentityDialog({ isOpen, onClose, onUpdated, status }: DialogProps) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setTyped("");
      setError(null);
    }
  }, [isOpen]);

  const did = status.identity?.did ?? "";

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const next = await revokeIdentity(typed);
      onUpdated(next);
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogShell
      footer={
        <>
          <Button isDisabled={busy} onPress={onClose} variant="secondary">
            Vazgec
          </Button>
          <Button isDisabled={busy || typed !== did} onPress={() => void submit()} variant="danger">
            {busy ? "Siliniyor..." : "Kimligi revoke et"}
          </Button>
        </>
      }
      isOpen={isOpen}
      onClose={onClose}
      title="Kimligi revoke et"
    >
      <Alert status="danger">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Bu islem geri alinamaz</Alert.Title>
          <Alert.Description>
            Kasa zarfi bu bilgisayardan silinir. Bu bir guvenli disk silme islemi{" "}
            <strong>degildir</strong>: yedeklerde, golge kopyalarda veya dosya
            sistemi gunlugunde iz kalabilir. Daha da onemlisi, daha once
            olusturdugunuz recovery dosyalari{" "}
            <strong>gecerli kalmaya devam eder</strong> ve parolasini bilen biri
            kimligi geri getirebilir.
          </Alert.Description>
        </Alert.Content>
      </Alert>

      <TextField className="w-full" onChange={setTyped} value={typed}>
        <Label>Onaylamak icin DID&apos;i tam olarak yazin</Label>
        <Input autoComplete="off" variant="secondary" />
      </TextField>
      <p className="font-mono text-xs break-all text-muted">{did}</p>

      {error !== null && <ErrorAlert message={error} title="Revoke edilemedi" />}
    </DialogShell>
  );
}
