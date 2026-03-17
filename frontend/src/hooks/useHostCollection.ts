import { startTransition, useEffect, useState } from 'react';
import { getHostApp, type OpenGuiclawApp, waitForHostApp } from '../bridge/openGuiclaw';

type UseHostCollectionOptions<T> = {
  eventName: string;
  load: (app: OpenGuiclawApp) => Promise<void>;
  snapshot: (app: OpenGuiclawApp) => T[];
};

export function useHostCollection<T>(options: UseHostCollectionOptions<T>) {
  const [hostApp, setHostApp] = useState<OpenGuiclawApp | null>(getHostApp());
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState('');

  useEffect(() => {
    let mounted = true;

    const syncFromHost = (app: OpenGuiclawApp) => {
      if (!mounted) return;
      startTransition(() => {
        setItems(options.snapshot(app));
        setLoading(false);
      });
    };

    waitForHostApp()
      .then(async (app) => {
        if (!mounted) return;
        setHostApp(app);
        await options.load(app);
        syncFromHost(app);
      })
      .catch((error: Error) => {
        if (!mounted) return;
        setErrorText(error.message);
        setLoading(false);
      });

    const handleUpdated = () => {
      const app = getHostApp();
      if (!app) return;
      syncFromHost(app);
    };

    window.addEventListener(options.eventName, handleUpdated);
    return () => {
      mounted = false;
      window.removeEventListener(options.eventName, handleUpdated);
    };
  }, []);

  return {
    hostApp,
    items,
    setItems,
    loading,
    errorText,
    setErrorText
  };
}
