import "@fontsource/vazirmatn/400.css";
import "@fontsource/vazirmatn/600.css";
import "@fontsource/vazirmatn/700.css";
import "@fontsource/vazirmatn/800.css";
import "@fontsource/lalezar/400.css";
import "./styles/app.css";
import "./styles/world.css";
import "./styles/scenes.css";
import "./styles/halls.css";
import "./styles/adventure.css";
import "./styles/clan.css";
import "./styles/themes.css";
import "./styles/battle.css";
import "./styles/chest.css";
import "./styles/game.css";
import "./styles/bazaar.css";
import "./styles/quests.css";
import "./styles/hero.css";
import "./styles/calm.css";
import "./styles/responsive.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 10_000 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
