"use client";

import { useState } from "react";

import { ChangePassword } from "@/components/change-password";

export function PasswordPage() {
  const [done, setDone] = useState(false);
  return (
    <div className="flex max-w-lg flex-col gap-4">
      <h1 className="text-3xl font-black tracking-tight text-ink sm:text-4xl">Change password</h1>
      {done ? (
        <p role="status" className="rounded-2xl bg-white p-4 font-semibold text-ink">
          Password changed. Your other sessions were signed out.
        </p>
      ) : (
        <ChangePassword onDone={() => setDone(true)} />
      )}
    </div>
  );
}
