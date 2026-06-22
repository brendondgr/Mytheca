import { SettingCard } from "@/components/feature/SettingCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
import type { Setting } from "@/lib/types";

/**
 * Settings column — one setting per row. The selected scenario's setting is
 * brought forward via the card's `active` state.
 */
export function SettingColumn({
  settings,
  activeId,
  query,
  onEdit,
}: {
  settings: Setting[];
  activeId: string;
  query: string;
  onEdit: (id: string) => void;
}) {
  return (
    <div>
      <ColumnHeader title="Settings" count={settings.length} hint="The places of this world." />
      {settings.length === 0 ? (
        <ColumnEmpty query={query} noun="settings" />
      ) : (
        <div className="flex flex-col gap-[14px]">
          {settings.map((s) => (
            <SettingCard
              key={s.id}
              setting={s}
              active={s.id === activeId}
              onEdit={() => onEdit(s.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
