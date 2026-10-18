import { createContext, useContext } from 'react';
import type { MoveRequest, ReorderRequest } from './types';

export interface BoardActions {
  columns: { key: string; label: string }[];
  maxPoints: number;
  onMove: (req: MoveRequest) => void;
  onReorder: (req: ReorderRequest) => void;
  onPointsSaved: () => void;
  onSettings: (projectId: string) => void;
}

export const ActionsContext = createContext<BoardActions | null>(null);

export function useActions(): BoardActions {
  const actions = useContext(ActionsContext);
  if (actions === null) throw new Error('useActions outside <ActionsContext>');
  return actions;
}
