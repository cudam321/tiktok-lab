import { Outlet } from "react-router-dom";
import Sidebar from "@/components/Sidebar";

export default function App() {
  return (
    <div className="min-h-screen flex bg-gray-950 text-gray-100">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
