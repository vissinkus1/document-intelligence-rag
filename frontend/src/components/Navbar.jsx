import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="brand-icon">◈</span>
        <span className="brand-text">DocQA</span>
      </div>

      <div className="navbar-links">
        <NavLink to="/chat" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
          Chat
        </NavLink>
        <NavLink to="/documents" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
          Documents
        </NavLink>
      </div>

      <div className="navbar-user">
        <span className="user-badge" data-role={user?.role}>
          {user?.role === "admin" ? "⚡" : "●"} {user?.email}
        </span>
        <button className="btn-logout" onClick={logout}>Sign Out</button>
      </div>
    </nav>
  );
}
