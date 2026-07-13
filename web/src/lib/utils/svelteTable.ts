import {
  createTable,
  functionalUpdate,
  type RowData,
  type Table,
  type TableOptions,
} from "@tanstack/table-core";
import { derived, writable, type Readable } from "svelte/store";

/** Minimal Svelte store adapter for TanStack Table core. */
export function createSvelteTable<TData extends RowData>(
  options: Readable<TableOptions<TData>>,
): Readable<Table<TData>> {
  const table = createTable<TData>({
    state: {},
    onStateChange: () => undefined,
    renderFallbackValue: null,
    ...getInitialOptions(options),
  });
  const state = writable(table.initialState);

  return derived([state, options], ([$state, $options]) => {
    table.setOptions((previous) => ({
      ...previous,
      ...$options,
      state: { ...$state, ...$options.state },
      onStateChange: (updater) => {
        state.update((current) => functionalUpdate(updater, current));
        $options.onStateChange?.(updater);
      },
    }));
    return table;
  });
}

function getInitialOptions<TData extends RowData>(
  options: Readable<TableOptions<TData>>,
): TableOptions<TData> {
  let initial!: TableOptions<TData>;
  const unsubscribe = options.subscribe((value) => (initial = value));
  unsubscribe();
  return initial;
}
