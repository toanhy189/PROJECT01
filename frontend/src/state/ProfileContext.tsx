/** Giữ hồ sơ trong bộ nhớ của tab; không ghi localStorage hoặc gửi cho LLM. */
import {
  createContext,
  useContext,
  useMemo,
  useState,
  useRef,
  type ReactNode,
  type Dispatch,
  type SetStateAction,
  type MutableRefObject,
} from 'react';
import { groups } from '../data/features';
import type { Analysis, Features } from '../types/api';

interface ProfileState {
  values: Record<string, string>;
  setValues: (values: Record<string, string>) => void;
  features: Features | null;
  snapshotKey: string;
  analysis: Analysis | null;
  setAnalysis: (value: Analysis | null) => void;
  analysisKey: string;
  setAnalysisKey: (value: string) => void;
  clear: () => void;
  messages: ChatMessage[];
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  shareProfile: boolean;
  setShareProfile: (value: boolean) => void;
  analysisSequence: MutableRefObject<number>;
}
export type ChatMessage = { id: string; question: string; result?: Analysis; error?: string };
const ProfileContext = createContext<ProfileState | null>(null);

/** Đổi form sang số chỉ khi mọi trường đã được điền và đúng miền khai báo. */
function completeFeatures(values: Record<string, string>): Features | null {
  const result: Features = {};
  for (const field of groups.flatMap((group) => group.fields)) {
    const raw = values[field.key];
    if (raw === undefined || raw.trim() === '') return null;
    const value = Number(raw);
    if (!Number.isFinite(value)) return null;
    if (field.options) {
      const minimum = ['Age', 'Education', 'Income', 'GenHlth'].includes(field.key) ? 1 : 0;
      if (!Number.isInteger(value) || value < minimum || value >= minimum + field.options.length)
        return null;
    } else if (
      value < field.min! ||
      value > field.max! ||
      (field.key !== 'BMI' && !Number.isInteger(value))
    )
      return null;
    result[field.key] = value;
  }
  return result;
}

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [values, setFormValues] = useState<Record<string, string>>({});
  const analysisSequence = useRef(0);
  const setValues = (next: Record<string, string>) => {
    analysisSequence.current += 1;
    setFormValues(next);
  };
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysisKey, setAnalysisKey] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [shareProfile, setShareProfile] = useState(false);
  const features = useMemo(() => completeFeatures(values), [values]);
  const snapshotKey = JSON.stringify(values);
  return (
    <ProfileContext.Provider
      value={{
        values,
        setValues,
        features,
        snapshotKey,
        analysis,
        setAnalysis,
        analysisKey,
        setAnalysisKey,
        messages,
        setMessages,
        shareProfile,
        setShareProfile,
        analysisSequence,
        clear: () => {
          setValues({});
          setAnalysis(null);
          setAnalysisKey('');
        },
      }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile() {
  const value = useContext(ProfileContext);
  if (!value) throw new Error('Thiếu bộ quản lý hồ sơ phiên.');
  return value;
}
