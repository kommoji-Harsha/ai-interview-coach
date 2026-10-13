"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createJobDescription,
  createSession,
  listJobDescriptions,
  listResumes,
  uploadResume,
} from "@/lib/api";
import {
  JobDescriptionMetadata,
  ResumeMetadata,
  SessionDifficulty,
} from "@/lib/types";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

const PRESET_ROLES = [
  {
    id: "backend",
    title: "Senior Backend Engineer",
    topics: ["system-design", "distributed-systems", "behavioral"],
  },
  {
    id: "frontend",
    title: "Frontend Software Engineer",
    topics: ["frontend-architecture", "accessibility", "behavioral"],
  },
  {
    id: "fullstack",
    title: "Full-Stack Engineer",
    topics: ["system-design", "api-design", "behavioral"],
  },
  {
    id: "ml",
    title: "Machine Learning Engineer",
    topics: ["ml-systems", "model-evaluation", "behavioral"],
  },
];

export default function OnboardingPage(): React.ReactElement {
  const router = useRouter();

  const [resumes, setResumes] = useState<ResumeMetadata[]>([]);
  const [jds, setJds] = useState<JobDescriptionMetadata[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Selected IDs
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [selectedJdId, setSelectedJdId] = useState<string>("");

  // Role selection & JD form
  const [selectedRolePreset, setSelectedRolePreset] =
    useState<string>("backend");
  const [company, setCompany] = useState("Acme Corp");
  const [roleTitle, setRoleTitle] = useState("Senior Backend Engineer");
  const [jdText, setJdText] = useState("");
  const [savingJd, setSavingJd] = useState(false);

  // Resume upload form
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeLabel, setResumeLabel] = useState("");
  const [uploadingResume, setUploadingResume] = useState(false);

  // Session config
  const [difficulty, setDifficulty] = useState<SessionDifficulty>("auto");
  const [maxTurns, setMaxTurns] = useState<number>(10);
  const [focusTopics, setFocusTopics] = useState<string>(
    "system-design, behavioral"
  );
  const [startingSession, setStartingSession] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadExistingAssets = useCallback(async () => {
    setInitialLoading(true);
    setLoadError(null);
    try {
      const [resumeList, jdList] = await Promise.all([
        listResumes(),
        listJobDescriptions(),
      ]);
      setResumes(resumeList.items);
      setJds(jdList.items);
      if (resumeList.items.length > 0) {
        setSelectedResumeId(resumeList.items[0].id);
      }
      if (jdList.items.length > 0) {
        setSelectedJdId(jdList.items[0].id);
      }
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? err.message
          : "Failed to load saved resumes and job descriptions."
      );
    } finally {
      setInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    loadExistingAssets();
  }, [loadExistingAssets]);

  const handleRolePresetSelect = (presetId: string) => {
    setSelectedRolePreset(presetId);
    const found = PRESET_ROLES.find((r) => r.id === presetId);
    if (found) {
      setRoleTitle(found.title);
      setFocusTopics(found.topics.join(", "));
    }
  };

  const handleResumeUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setActionError(null);
    if (!resumeFile) {
      setActionError("Please select a PDF or DOCX resume file to upload.");
      return;
    }

    setUploadingResume(true);
    try {
      const created = await uploadResume(resumeFile, resumeLabel);
      setResumes((prev) => [created, ...prev]);
      setSelectedResumeId(created.id);
      setResumeFile(null);
      setResumeLabel("");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Resume upload failed."
      );
    } finally {
      setUploadingResume(false);
    }
  };

  const handleSaveJobDescription = async (
    e: React.FormEvent<HTMLFormElement>
  ) => {
    e.preventDefault();
    setActionError(null);
    if (!company.trim() || !roleTitle.trim() || !jdText.trim()) {
      setActionError(
        "Please provide company name, role title, and job description text."
      );
      return;
    }

    setSavingJd(true);
    try {
      const created = await createJobDescription({
        company: company.trim(),
        role_title: roleTitle.trim(),
        raw_text: jdText.trim(),
      });
      setJds((prev) => [created, ...prev]);
      setSelectedJdId(created.id);
      setJdText("");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to save job description."
      );
    } finally {
      setSavingJd(false);
    }
  };

  const handleStartSession = async () => {
    setActionError(null);
    if (!selectedResumeId || !selectedJdId) {
      setActionError(
        "Please select or create both a resume and a job description before starting."
      );
      return;
    }

    setStartingSession(true);
    try {
      const topics = focusTopics
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const session = await createSession({
        resume_id: selectedResumeId,
        jd_id: selectedJdId,
        config: {
          difficulty,
          max_turns: maxTurns,
          focus_topics: topics.length > 0 ? topics : undefined,
        },
      });
      router.push(`/sessions/${session.id}`);
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to start interview session."
      );
    } finally {
      setStartingSession(false);
    }
  };

  if (initialLoading) {
    return <LoadingState message="Loading your onboarding workspace..." />;
  }

  if (loadError) {
    return (
      <ErrorState
        title="Could not load onboarding data"
        message={loadError}
        onRetry={loadExistingAssets}
      />
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">
          Interview Setup & Onboarding
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Select your target role, upload your resume, and paste the job
          description to tailor your mock interview.
        </p>
      </div>

      {actionError && (
        <ErrorState title="Action Required" message={actionError} />
      )}

      {/* Step 1: Role Selection */}
      <section
        aria-labelledby="role-selection-heading"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2
          id="role-selection-heading"
          className="text-lg font-bold text-slate-900"
        >
          1. Select Target Role
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Choose a role template to pre-configure focus topics or customize
          below.
        </p>
        <div
          role="radiogroup"
          aria-label="Target role templates"
          className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        >
          {PRESET_ROLES.map((role) => {
            const active = selectedRolePreset === role.id;
            return (
              <button
                key={role.id}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => handleRolePresetSelect(role.id)}
                className={`flex flex-col items-start rounded-xl border p-4 text-left transition ${
                  active
                    ? "border-indigo-600 bg-indigo-50/70 ring-2 ring-indigo-600"
                    : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <span className="text-sm font-semibold text-slate-900">
                  {role.title}
                </span>
                <span className="mt-1 text-xs text-slate-500">
                  Topics: {role.topics.join(", ")}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Step 2: Resume Upload & Selection */}
        <section
          aria-labelledby="resume-section-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2
            id="resume-section-heading"
            className="text-lg font-bold text-slate-900"
          >
            2. Upload or Choose Resume
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Supported formats: PDF or DOCX (max 5 MB).
          </p>

          <form onSubmit={handleResumeUpload} className="mt-4 space-y-4">
            <div>
              <label
                htmlFor="resume-label-input"
                className="block text-sm font-medium text-slate-700"
              >
                Resume Label (Optional)
              </label>
              <input
                id="resume-label-input"
                type="text"
                value={resumeLabel}
                onChange={(e) => setResumeLabel(e.target.value)}
                placeholder="e.g., SWE Resume 2026"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label
                htmlFor="resume-file-input"
                className="block text-sm font-medium text-slate-700"
              >
                Resume File (PDF or DOCX)
              </label>
              <input
                id="resume-file-input"
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(e) => setResumeFile(e.target.files?.[0] || null)}
                className="mt-1 block w-full text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-indigo-700 hover:file:bg-indigo-100"
              />
            </div>

            <button
              type="submit"
              disabled={uploadingResume}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {uploadingResume ? "Uploading Resume..." : "Upload Resume"}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-100 pt-4">
            <label
              htmlFor="existing-resume-select"
              className="block text-sm font-medium text-slate-700"
            >
              Selected Resume
            </label>
            {resumes.length === 0 ? (
              <div className="mt-2">
                <EmptyState
                  title="No resumes uploaded"
                  description="Upload a PDF or DOCX resume above to use in your interview."
                />
              </div>
            ) : (
              <select
                id="existing-resume-select"
                value={selectedResumeId}
                onChange={(e) => setSelectedResumeId(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label ? `${r.label} (${r.filename})` : r.filename} —{" "}
                    {r.char_count} chars
                  </option>
                ))}
              </select>
            )}
          </div>
        </section>

        {/* Step 3: Job Description Paste & Selection */}
        <section
          aria-labelledby="jd-section-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2
            id="jd-section-heading"
            className="text-lg font-bold text-slate-900"
          >
            3. Paste Job Description
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Paste the job description so questions match the role requirements.
          </p>

          <form onSubmit={handleSaveJobDescription} className="mt-4 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="jd-company-input"
                  className="block text-sm font-medium text-slate-700"
                >
                  Company
                </label>
                <input
                  id="jd-company-input"
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="Acme Corp"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label
                  htmlFor="jd-role-input"
                  className="block text-sm font-medium text-slate-700"
                >
                  Role Title
                </label>
                <input
                  id="jd-role-input"
                  type="text"
                  value={roleTitle}
                  onChange={(e) => setRoleTitle(e.target.value)}
                  placeholder="Senior Backend Engineer"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="jd-raw-text"
                className="block text-sm font-medium text-slate-700"
              >
                Job Description Text
              </label>
              <textarea
                id="jd-raw-text"
                rows={4}
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the responsibilities and qualifications here..."
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            <button
              type="submit"
              disabled={savingJd}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {savingJd ? "Saving JD..." : "Save Job Description"}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-100 pt-4">
            <label
              htmlFor="existing-jd-select"
              className="block text-sm font-medium text-slate-700"
            >
              Selected Job Description
            </label>
            {jds.length === 0 ? (
              <div className="mt-2">
                <EmptyState
                  title="No job descriptions saved"
                  description="Paste and save a job description above to continue."
                />
              </div>
            ) : (
              <select
                id="existing-jd-select"
                value={selectedJdId}
                onChange={(e) => setSelectedJdId(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                {jds.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.company} — {j.role_title} ({j.char_count} chars)
                  </option>
                ))}
              </select>
            )}
          </div>
        </section>
      </div>

      {/* Step 4: Session Configuration & Launch */}
      <section
        aria-labelledby="session-config-heading"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2
          id="session-config-heading"
          className="text-lg font-bold text-slate-900"
        >
          4. Configure & Start Interview
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <label
              htmlFor="session-difficulty"
              className="block text-sm font-medium text-slate-700"
            >
              Difficulty
            </label>
            <select
              id="session-difficulty"
              value={difficulty}
              onChange={(e) =>
                setDifficulty(e.target.value as SessionDifficulty)
              }
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="auto">Adaptive (Auto)</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="session-max-turns"
              className="block text-sm font-medium text-slate-700"
            >
              Max Turns
            </label>
            <input
              id="session-max-turns"
              type="number"
              min={1}
              max={25}
              value={maxTurns}
              onChange={(e) => setMaxTurns(Number(e.target.value) || 10)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label
              htmlFor="session-focus-topics"
              className="block text-sm font-medium text-slate-700"
            >
              Focus Topics (comma-separated)
            </label>
            <input
              id="session-focus-topics"
              type="text"
              value={focusTopics}
              onChange={(e) => setFocusTopics(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            disabled={startingSession || !selectedResumeId || !selectedJdId}
            onClick={handleStartSession}
            className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {startingSession
              ? "Launching Interview Session..."
              : "Start Mock Interview"}
          </button>
        </div>
      </section>
    </div>
  );
}
