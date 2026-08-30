interface EmptyStateProps {
  readonly title: string;
  readonly description: string;
}

/**
 * Honest empty state. It says what is absent and never invents a placeholder
 * identity, DID or record to fill the space.
 */
export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border px-6 py-10 text-center">
      <p className="text-base font-medium text-foreground">{title}</p>
      <p className="max-w-prose text-sm text-muted">{description}</p>
    </div>
  );
}
