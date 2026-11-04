import { Link } from "react-router-dom";
import { useAuth } from "../auth";

function AppHeader() {
    const { user, logout } = useAuth();

    return (
        <header className="app-header">
            <Link to="/">My Boards</Link>
            <div className="app-header-account">
                <span>Signed in as <strong>{user?.full_name || user?.username}</strong></span>
                <button onClick={logout}>Log out</button>
            </div>
        </header>
    );
}

export default AppHeader;
