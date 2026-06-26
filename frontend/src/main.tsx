import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "./index.css";
import App from "./App";
import Dashboard from "./pages/Dashboard";
import Analytics from "./pages/Analytics";
import PostManager from "./pages/PostManager";
import Lab from "./pages/Lab";
import Workshop from "./pages/Workshop";
import Production from "./pages/Production";
import Agent from "./pages/Agent";
import Settings from "./pages/Settings";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Dashboard />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="posts" element={<PostManager />} />
          <Route path="workshop" element={<Workshop />} />
          <Route path="produce" element={<Production />} />
          <Route path="lab" element={<Lab />} />
          <Route path="experiments" element={<Navigate to="/lab" replace />} />
          <Route path="agent" element={<Agent />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
