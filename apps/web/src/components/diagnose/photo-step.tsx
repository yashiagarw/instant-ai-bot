"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { Camera, CircleCheck, ImagePlus, LoaderCircle, RotateCcw, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  errorMessage,
  PHOTO_MAX_BYTES,
  photosApi,
  photoType,
  sendToStorage,
  type Photo,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_PHOTOS = 5;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

type Step =
  | { kind: "idle" }
  | { kind: "preview"; file: File; url: string | null }
  | { kind: "uploading"; file: File; url: string | null; progress: number; checking: boolean }
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

/** What is wrong with the file before anything is sent, or null. The API checks again from the file itself. */
export function checkPhoto(file: File): string | null {
  if (!photoType(file)) return "This file is not a photo we can use. Please send a JPEG, PNG, WebP or HEIC photo.";
  if (file.size > PHOTO_MAX_BYTES) return "This photo is too big. Please use one under 10 MB.";
  if (file.size === 0) return "This file is empty. Please take or choose another photo.";
  return null;
}

/** An optional photo of the problem, beside the questions. It never blocks them: skip it, or carry on while it
 * uploads; an error here only affects the photo. */
export function PhotoStep({ sessionId }: { sessionId: string }) {
  const id = useId();
  const touch = useTouch();
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [skipped, setSkipped] = useState(false);
  const [status, setStatus] = useState("");

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
    const problem = checkPhoto(file);
    // Most browsers cannot show HEIC: no preview then, the server converts it.
    const url = problem || photoType(file) === "image/heic" ? null : URL.createObjectURL(file);
    setStatus("");
    setStep(problem ? { kind: "error", file: null, url: null, message: problem } : { kind: "preview", file, url });
  }

  async function upload(file: File, url: string | null) {
    const type = photoType(file)!;
    abort.current = new AbortController();
    setStep({ kind: "uploading", file, url, progress: 0, checking: false });
    try {
      const form = await photosApi.start(sessionId, type, file.size);
      await sendToStorage(
        form,
        file,
        (p) => setStep((s) => (s.kind === "uploading" ? { ...s, progress: p } : s)),
        abort.current.signal,
      );
      setStep((s) => (s.kind === "uploading" ? { ...s, progress: 1, checking: true } : s));
      const photo = await photosApi.complete(form.upload_id);
      setPhotos((ps) => [...ps, photo]);
      setStep({ kind: "idle" });
      setStatus("Photo added. The mechanic will see it with your diagnosis.");
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
      setStatus("Photo removed.");
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
          {again ? "Retake" : "Take a photo"}
        </Button>
      )}
      <Button type="button" variant="outline" className="h-12 rounded-full border-2 px-5 text-base font-bold" onClick={() => gallery.current?.click()}>
        <ImagePlus aria-hidden="true" className="size-5" />
        {touch ? (again ? "Choose another" : "Choose from gallery") : again ? "Choose another photo" : "Choose a photo"}
      </Button>
    </div>
  );

  if (skipped && photos.length === 0 && step.kind === "idle") {
    return (
      <p className="text-ink/75">
        No photo added.{" "}
        <button
          type="button"
          onClick={() => setSkipped(false)}
          className="min-h-11 rounded-full font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          Add a photo
        </button>
      </p>
    );
  }

  return (
    <section aria-labelledby={`${id}-h`} className="flex flex-col gap-4 rounded-3xl border border-border bg-white p-5" data-testid="photo-step">
      {inputs}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id={`${id}-h`} className="text-lg font-black text-ink">
            Add a photo <span className="font-semibold text-ink/60">(optional)</span>
          </h2>
          <p className="text-sm text-ink/75">
            A photo of the problem (a leak, a warning light, the tyre) helps the mechanic. You can skip this.
          </p>
        </div>
        {photos.length === 0 && step.kind === "idle" && (
          <button
            type="button"
            onClick={() => setSkipped(true)}
            className="min-h-11 shrink-0 rounded-full px-3 font-bold text-orange-text underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
          >
            Skip
          </button>
        )}
      </div>

      {photos.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="photos">
          {photos.map((p, i) => (
            <li key={p.id} className="relative overflow-hidden rounded-2xl bg-warm-white">
              {p.url ? (
                // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the API
                <img src={p.url} alt={`Your photo ${i + 1}`} className="aspect-square w-full object-cover" />
              ) : (
                <div className="flex aspect-square items-center justify-center text-sm text-ink/70">Photo {i + 1}</div>
              )}
              <button
                type="button"
                onClick={() => void remove(p)}
                aria-label={`Remove photo ${i + 1}`}
                className="absolute top-1.5 right-1.5 flex size-11 items-center justify-center rounded-full bg-white/90 text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring"
              >
                <Trash2 aria-hidden="true" className="size-5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {(step.kind === "preview" || step.kind === "uploading") && (
        <div className="flex flex-col gap-3">
          <div className="overflow-hidden rounded-2xl bg-warm-white">
            {step.url ? (
              // eslint-disable-next-line @next/next/no-img-element -- local preview (object URL)
              <img src={step.url} alt="Preview of your photo" className="max-h-80 w-full object-contain" />
            ) : (
              <p className="p-4 text-ink/80">
                {step.file.name}: preview not available on this device. We will convert it when you upload.
              </p>
            )}
          </div>
          {step.kind === "preview" ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="button" className="h-12 rounded-full bg-cta px-6 text-lg font-bold text-white hover:bg-cta/90" onClick={() => void upload(step.file, step.url)}>
                Use this photo
              </Button>
              {chooseButtons(true)}
              <Button type="button" variant="ghost" className="h-12 rounded-full px-4 text-base font-semibold" onClick={() => setStep({ kind: "idle" })}>
                <X aria-hidden="true" className="size-5" />
                Cancel
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-sm font-semibold text-ink">
                <span>{step.checking ? "Checking and removing location data…" : "Uploading…"}</span>
                <span className="tabular-nums">{Math.round(step.progress * 100)}%</span>
              </div>
              <div
                role="progressbar"
                aria-label="Photo upload"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(step.progress * 100)}
                className="h-2.5 overflow-hidden rounded-full bg-ink/10"
              >
                <div
                  className={cn("h-full rounded-full bg-cta transition-[width] motion-reduce:transition-none", step.checking && "animate-pulse")}
                  style={{ width: `${Math.round(step.progress * 100)}%` }}
                />
              </div>
              {!step.checking && (
                <Button type="button" variant="ghost" className="h-11 self-start rounded-full px-3 text-base font-semibold" onClick={() => abort.current?.abort()}>
                  <LoaderCircle aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
                  Cancel upload
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
                Try again
              </Button>
            )}
            {chooseButtons(true)}
            <Button type="button" variant="ghost" className="h-12 rounded-full px-4 text-base font-semibold" onClick={() => setStep({ kind: "idle" })}>
              Never mind
            </Button>
          </div>
        </div>
      )}

      {step.kind === "idle" && photos.length < MAX_PHOTOS && chooseButtons(false)}

      <p className="flex items-center gap-2 text-sm text-ink/80" aria-live="polite" data-testid="photo-status">
        {status && <CircleCheck aria-hidden="true" className="size-4 text-success" />}
        {status}
      </p>
      <p className="text-xs text-ink/60">
        JPEG, PNG, WebP or HEIC, up to 10 MB. We remove location and camera details before saving. Only you and our
        team can see your photos.
      </p>
    </section>
  );
}
