import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  BarChart3,
  FileVideo,
  FlaskConical,
  Bot,
  Settings,
  SlidersHorizontal,
  Clapperboard,
} from "lucide-react";

const links = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/analytics", icon: BarChart3, label: "Analytics" },
  { to: "/posts", icon: FileVideo, label: "Posts" },
  { to: "/workshop", icon: SlidersHorizontal, label: "Workshop" },
  { to: "/produce", icon: Clapperboard, label: "Produce" },
  { to: "/lab", icon: FlaskConical, label: "Lab" },
  { to: "/agent", icon: Bot, label: "Agent" },
];

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 bg-gray-950 flex flex-col">
      <div className="px-5 py-5">
        <span className="text-lg font-bold tracking-tight text-white">
          TikTok Lab
        </span>
      </div>

      <nav className="flex-1 px-3 space-y-0.5">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-900"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 pb-4">
        <NavLink
          to="/settings"
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 hover:text-gray-300 hover:bg-gray-900 transition-colors"
        >
          <Settings size={18} />
          Settings
        </NavLink>
      </div>
    </aside>
  );
}
