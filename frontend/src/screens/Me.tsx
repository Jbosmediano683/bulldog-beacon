import { useState } from "react";
import { api, type Contact, type User } from "../api";
import { IconX } from "../icons";
import { useApp } from "../state";

export default function Me({ onUsage, onSignOut }: { onUsage: () => void; onSignOut: () => void }) {
  const { user, setUser, toast } = useApp();
  const [contacts, setContacts] = useState<Contact[]>(user.contacts);
  const [medical, setMedical] = useState(user.medical_note);

  async function save() {
    const u = await api<User>("/api/profile", { method: "PUT", body: { contacts, medical_note: medical } });
    setUser(u);
    toast("Profile saved");
  }

  return (
    <div className="stack">
      <div>
        <div className="h2">{user.name}</div>
        <div className="small muted">NetID {user.netid} · {user.affiliation}{user.unit ? ` · ${user.unit}` : ""}</div>
      </div>

      {user.role !== "dispatcher" && (
        <>
          <div className="field">
            <label>Trusted contacts (alerted on SOS or a missed walk check-in)</label>
            {contacts.map((c, i) => (
              <div className="row" key={i}>
                <input className="input" value={c.name} placeholder="Name"
                       onChange={(e) => setContacts(contacts.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <input className="input" value={c.phone} placeholder="Phone"
                       onChange={(e) => setContacts(contacts.map((x, j) => (j === i ? { ...x, phone: e.target.value } : x)))} />
                <button className="btn sm ghost" onClick={() => setContacts(contacts.filter((_, j) => j !== i))} aria-label="Remove"><IconX size={16} /></button>
              </div>
            ))}
            {contacts.length < 5 && (
              <button className="btn sm" style={{ alignSelf: "flex-start" }} onClick={() => setContacts([...contacts, { name: "", phone: "" }])}>
                + Add contact
              </button>
            )}
          </div>
          <div className="field">
            <label>Medical note for responders (optional, only shared during an SOS)</label>
            <input className="input" value={medical} maxLength={300} placeholder="e.g. Type 1 diabetes, asthma, allergies"
                   onChange={(e) => setMedical(e.target.value)} />
          </div>
          <button className="btn primary" onClick={save}>Save profile</button>
        </>
      )}
      <div className="divider" />
      <button className="btn" onClick={onUsage}>AI usage and safety log</button>
      <button className="btn ghost" onClick={onSignOut}>Sign out</button>
      <div className="tiny faint">
        Bulldog Beacon is an independent student project (MGT 409, Yale School of Management). It is not an official Yale University service and is not affiliated with or endorsed by Yale University. In an emergency, call 911. SOS, escort requests, and contact alerts are simulated; nothing is sent to Yale PD or your contacts.
      </div>
    </div>
  );
}
