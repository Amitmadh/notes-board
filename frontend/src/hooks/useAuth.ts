import { useContext } from "react";
import { AuthContext } from "../auth";

export function useAuth() {
    const auth = useContext(AuthContext);
    if (!auth) throw new Error("useAuth must be used inside an AuthProvider");
    return auth;
}
