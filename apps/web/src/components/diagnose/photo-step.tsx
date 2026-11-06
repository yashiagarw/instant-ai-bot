"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { Camera, CircleCheck, ImagePlus, LoaderCircle, RotateCcw, Trash2, X } from "lucide-react";
import { useTranslations } from "next-intl";

import { PhotoFindings, photoAlerts } from "@/components/diagnose/photo-findings";
import { SafetyBanner } from "@/components/safety-banner";
import { Button } from "@/components/ui/button";
import {
  errorMessage,
  type Finding,
  PHOTO_MAX_BYTES,
  type PhotoMode,
  photosApi,
  photoType,
  sendToStorage,
  type Photo,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import en from "@/i18n/messages/site.en.json";

const MAX_PHOTOS = 5;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

type Step =
  | { kind: "idle" }
  | { kind: "preview"; file: File; url: string | null }
  | { kind: "uploading"; file: File; url: string | null; progress: number; phase: "sending" | "checking" | "reading" }
  | { kind: "error"; file: File | null; url: string | null; message: string };

/** Phones get "Take a photo" (camera) and "Choose from gallery"; desktops one "Choose a photo". */
function useTouch(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia?.("(pointer: coarse)");
      mq?.addEventListener?.("change", onChange);
      return () => mq?.removeEventListener?.("change", onChange);
    },
    () => window.matchMedia?.("(pointer: coarse)").matches ?? false,
    () => false,
  );
}

type PhotoProblem = "badType" | "tooBig" | "empty";

/** What is wrong with the file before anything is sent (a message key), or null. The API checks again. */
export function photoProblem(file: File): PhotoProblem | null {
  if (!photoType(file)) return "badType";
  if (file.size > PHOTO_MAX_BYTES) return "tooBig";
  if (file.size === 0) return "empty";
  return null;
}

/** The same, as an English sentence. */
export function checkPhoto(file: File): string | null {
  const problem = photoProblem(file);
  return problem ? en.diagnose.photo[problem] : null;
}

const MODES: { value: PhotoMode; key: "modeWarning" | "modeDamage" }[] = [
  { value: "warning_light", key: "modeWarning" },
  { value: "damage", key: "modeDamage" },
];

/** An optional photo of the problem, beside the questions. It never blocks them: skip it, or carry on while it
 * uploads; an error here only affects the photo. After upload the photo is read for a warning light or damage;
 * when that is not possible a mechanic looks at it. */
export function PhotoStep({ sessionId, defaultMode = "damage" }: { sessionId: string; defaultMode?: PhotoMode }) {
  const t = useTranslations("diagnose.photo");
  const tc = useTranslations("common");
  const id = useId();
  const touch = useTouch();
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [skipped, setSkipped] = useState(false);
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState<PhotoMode>(defaultMode);

  // Photos already added to this diagnosis (after a reload). Failure here just shows none.
  useEffect(() => {
    const ctrl = new AbortController();
    photosApi
      .list(sessionId, ctrl.signal)
      .then(setPhotos)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [sessionId]);

  // Object URLs for previews are released when the preview goes away.
  const previewUrl = step.kind === "idle" ? null : step.url;
  useEffect(() => () => void (previewUrl && URL.revokeObjectURL(previewUrl)), [previewUrl]);

  function pick(file: File | undefined) {
    if (!file) return;
    const key = photoProblem(file);
    const problem = key ? t(key) : null;
    // Most browsers cannot show HEIC: no preview then, the server converts it.
    const url = problem || photoType(file) === "image/heic" ? null : URL.createObjectURL(file);
    setStatus("");
    setStep(problem ? { kind: "error", file: null, url: null, message: problem } : { kind: "preview", file, url });
  }

  async function upload(file: File, url: string | null) {
    const type = photoType(file)!;
    abort.current = new AbortController();
    setStep({ kind: "uploading", file, url, progress: 0, phase: "sending" });
    try {
      const form = await photosApi.start(sessionId, type, file.size);
      await sendToStorage(
        form,
        file,
        (p) => setStep((s) => (s.kind === "uploading" ? { ...s, progress: p } : s)),
        abort.current.signal,
      );
      setStep((s) => (s.kind === "uploading" ? { ...s, progress: 1, phase: "checking" } : s));
      const photo = await photosApi.complete(form.upload_id);
      setStep((s) => (s.kind === "uploading" ? { ...s, phase: "reading" } : s));
      // Reading the photo is extra: if it fails, the photo is still saved and a mechanic looks at it.
      const finding: Finding | null = await photosApi.analyze(photo.id, mode).catch(() => null);
      setPhotos((ps) => [...ps, { ...photo, findings: finding ? [finding] : [] }]);
      setStep({ kind: "idle" });
      setStatus(t("added"));
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setStep({ kind: "preview", file, url });
        return;
      }
      setStep({ kind: "error", file, url, message: errorMessage(e) });
    }
  }

  async function remove(photo: Photo) {
    try {
      await photosApi.remove(photo.id);
      setPhotos((ps) => ps.filter((p) => p.id !== photo.id));
      setStatus(t("removed"));
    } catch (e) {
      setStatus(errorMessage(e));
    }
  }

  const inputs = (
    <>
      <input
        ref={camera}
        type="file"
        accept={ACCEPT}
        capture="environment"
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="camera-input"
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <input
        ref={gallery}
        type="file"
        accept={ACCEPT}
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="gallery-input"
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </>
  );
  const chooseButtons = (again = false) => (
    <div className="flex flex-col gap-2 sm:flex-row">
      {touch && (
        <Button type="button" variant="outline" className="h-12 rounded-full border-2 px-5 text-base font-bold" onClick={() => camera.current?.click()}>
          <Camera aria-hidden="true" className="size-5" />
          {again ? t("retake") : t("take")}
        </Button>
      )}
      <Button type="button" variant="outline" className="h-12 rounded-full border-2 px-5 text-base font-bold" onClick={() => gallery.current?.click()}>
        <ImagePlus aria-hidden="true" className="size-5" />
        {touch ? (again ? t("chooseAnother") : t("fromGallery")) : again ? t("chooseAnotherPhoto") : t("choose")}
      </Button>
    </div>
  );

  if (skipped && photos.length === 0 && step.kind === "idle") {
    return (
      <p className="text-ink/75">
        {t("skipped")}{" "}
        <button
          type="button"
          onClick={() => setSkipped(false)}
          className="min-h-11 rounded-full font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          {t("add")}
        </button>
      </p>
    );
  }

  return (
    <section aria-labelledby={`${id}-h`} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-5" data-testid="photo-step">
      {inputs}
      <SafetyBanner alerts={photoAlerts(photos)} />
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id={`${id}-h`} className="text-lg font-black text-ink">
            {t("title")} <span className="font-semibold text-ink/70">{t("optional")}</span>
          </h2>
          <p className="text-sm text-ink/75">
            {t("intro")}
          </p>
        </div>
        {photos.length === 0 && step.kind === "idle" && (
          <button
            type="button"
            onClick={() => setSkipped(true)}
            className="min-h-11 shrink-0 rounded-full px-3 font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
          >
            {t("skip")}
          </button>
        )}
      </div>

      {photos.length > 0 && (
        <ul className="flex flex-col gap-3" data-testid="photos">
          {photos.map((p, i) => (
            <li key={p.id} className="flex gap-3">
              <div className="relative size-28 shrink-0 overflow-hidden rounded-2xl bg-warm-white">
              {p.url ? (
                // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the API
                <img src={p.url} alt={t("yours", { n: i + 1 })} className="size-full object-cover" />
              ) : (
                <div className="flex size-full items-center justify-center text-sm text-ink/70">{t("placeholder", { n: i + 1 })}</div>
              )}
              <button
                type="button"
                onClick={() => void remove(p)}
                aria-label={t("remove", { n: i + 1 })}
                className="absolute top-1.5 right-1.5 flex size-11 items-center justify-center rounded-full bg-white/90 text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Trash2 aria-hidden="true" className="size-5" />
              </button>
              </div>
              <div className="min-w-0 flex-1">
                <PhotoFindings findings={p.findings ?? []} />
              </div>
            </li>
          ))}
        </ul>
      )}

      {(step.kind === "preview" || step.kind === "uploading") && (
        <div className="flex flex-col gap-3">
          <div className="overflow-hidden rounded-2xl bg-warm-white">
            {step.url ? (
              // eslint-disable-next-line @next/next/no-img-element -- local preview (object URL)
              <img src={step.url} alt={t("preview")} className="max-h-80 w-full object-contain" />
            ) : (
              <p className="p-4 text-ink/80">
                {t("noPreview", { name: step.file.name })}
              </p>
            )}
          </div>
          {step.kind === "preview" && (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 font-bold text-ink">{t("whatShows")}</legend>
              <div className="flex flex-col gap-2 sm:flex-row">
                {MODES.map((m) => (
                  <label
                    key={m.value}
                    className={cn(
                      "flex min-h-11 cursor-pointer items-center gap-2 rounded-full border-2 px-4 py-2 font-semibold text-ink has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring",
                      mode === m.value ? "border-cta bg-warm-white" : "border-border bg-white",
                    )}
                  >
                    <input
                      type="radio"
                      name={`${id}-mode`}
                      value={m.value}
                      checked={mode === m.value}
                      onChange={() => setMode(m.value)}
                      className="size-5 accent-cta"
                    />
                    {t(m.key)}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {step.kind === "preview" ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="button" className="h-12 rounded-full bg-cta px-6 text-lg font-bold text-white hover:bg-cta/90" onClick={() => void upload(step.file, step.url)}>
                {t("use")}
              </Button>
              {chooseButtons(true)}
              <Button type="button" variant="ghost" className="h-12 rounded-full px-4 text-base font-semibold" onClick={() => setStep({ kind: "idle" })}>
                <X aria-hidden="true" className="size-5" />
                {t("cancel")}
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-sm font-semibold text-ink">
                <span>
                  {step.phase === "sending" ? t("uploading") : step.phase === "checking" ? t("checking") : t("reading")}
                </span>
                <span className="tabular-nums">{Math.round(step.progress * 100)}%</span>
              </div>
              <div
                role="progressbar"
                aria-label={t("progress")}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(step.progress * 100)}
                className="h-2.5 overflow-hidden rounded-full bg-ink/10"
              >
                <div
                  className={cn(
                    "h-full rounded-full bg-cta transition-[width] motion-reduce:transition-none",
                    step.phase !== "sending" && "animate-pulse motion-reduce:animate-none",
                  )}
                  style={{ width: `${Math.round(step.progress * 100)}%` }}
                />
              </div>
              {step.phase === "sending" && (
                <Button type="button" variant="ghost" className="h-11 self-start rounded-full px-3 text-base font-semibold" onClick={() => abort.current?.abort()}>
                  <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
                  {t("cancelUpload")}
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {step.kind === "error" && (
        <div className="flex flex-col gap-3">
          <p role="alert" className="font-semibold text-orange-text">
            {step.message}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            {step.file && (
              <Button type="button" variant="outline" className="h-12 rounded-full border-2 px-5 text-base font-bold" onClick={() => void upload(step.file!, step.url)}>
                <RotateCcw aria-hidden="true" className="size-5" />
                {tc("tryAgain")}
              </Button>
            )}
            {chooseButtons(true)}
            <Button type="button" variant="ghost" className="h-12 rounded-full px-4 text-base font-semibold" onClick={() => setStep({ kind: "idle" })}>
              {t("neverMind")}
            </Button>
          </div>
        </div>
      )}

      {step.kind === "idle" && photos.length < MAX_PHOTOS && chooseButtons(false)}

      <p className="flex items-center gap-2 text-sm text-ink/80" aria-live="polite" data-testid="photo-status">
        {status && <CircleCheck aria-hidden="true" className="size-4 text-success" />}
        {status}
      </p>
      <p className="text-xs text-ink/70">
        {t("rules")}
      </p>
    </section>
  );
}
