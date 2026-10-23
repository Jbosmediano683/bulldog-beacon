import { useEffect, useState } from "react";
import { api, type User } from "./api";
import Login from "./screens/Login";
import Shell from "./Shell";
import Skyline from "./components/Skyline";
import { AppProvider } from "./state";

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api<User>("/api/auth/me").then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) return <Skyline />;
  if (user === null) {
    return (
      <>
        <Skyline />
        <Login onSignedIn={setUser} />
      </>
    );
  }
  return (
    <AppProvider key={user.id} user={user} setUser={setUser}>
      <Skyline />
      <Shell />
    </AppProvider>
  );
}
