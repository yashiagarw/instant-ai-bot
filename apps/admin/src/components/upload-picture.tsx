"use client";

import { useId, useState } from "react";
import { Upload } from "lucide-react";

import { adminApi, errorMessage, type Picture } from "@/lib/api";

/** Upload a picture (JPEG, PNG, WebP or HEIC) to the photo storage; the API checks it, strips its metadata and keeps a
 * clean JPEG. The caller links it (to a fault or a part) in the draft. */
export function UploadPicture({ onUploaded }: { onUploaded: (p: Picture) => void }) {
  const id = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={id}
        className="inline-flex h-11 cursor-pointer items-center gap-2 rounded-full border border-input bg-white px-5 font-semibold text-ink focus-within:ring-3 focus-within:ring-ring hover:bg-warm-white"
      >
        <Upload aria-hidden="true" className="size-5" />
        {busy ? "Uploading…" : "Upload a picture"}
        <input
          id={id}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            setBusy(true);
            setError("");
            adminApi
              .uploadPicture(file, file.name.replace(/\.[^.]+$/, ""))
              .then(onUploaded)
              .catch((err) => setError(errorMessage(err)))
              .finally(() => setBusy(false));
          }}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm font-semibold text-orange-text">
          {error}
        </p>
      )}
    </div>
  );
}
