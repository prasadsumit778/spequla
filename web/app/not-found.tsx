import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <p className="label-caps">Page not found</p>
      <h1 className="mt-2 text-[20px] font-semibold">That screen does not exist</h1>
      <p className="mt-2 text-[13.5px] text-ink-muted">
        The link may be out of date. Nothing has changed in your data.
      </p>
      <Link
        href="/overview"
        className="mt-5 inline-flex h-9 items-center rounded-control border border-brand-700 bg-brand-700 px-4 text-sm font-medium text-white hover:bg-brand-800"
      >
        Go to the overview
      </Link>
    </div>
  );
}
