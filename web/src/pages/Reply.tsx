import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Brand } from "../components/PublicNav";
import { ErrorState, Skeleton } from "../components/States";
import { ApiError, userMessage } from "../lib/http";

type Lang = "en" | "hi" | "mr" | "kn";
const LANGS: { id: Lang; name: string }[] = [{ id: "en", name: "English" }, { id: "hi", name: "हिन्दी" }, { id: "mr", name: "मराठी" }, { id: "kn", name: "ಕನ್ನಡ" }];

// Plain, neutral wording: the question never suggests an answer.
const TEXT: Record<Lang, { title: string; ask: (c: string, w: string) => string; yes: string; partly: string; no: string; thanks: string; thanksNote: string; used: string; expired: string }> = {
  en: { title: "Was it fixed?", ask: (c, w) => `A complaint about ${c} in ${w} was marked as fixed. Was the problem actually fixed?`, yes: "Yes, it was fixed", partly: "Partly fixed", no: "No, it is not fixed", thanks: "Thank you", thanksNote: "Your answer was recorded. A person reviews every case before anything is reopened.", used: "This link has already been used.", expired: "This link has expired." },
  hi: { title: "क्या यह ठीक हुआ?", ask: (c, w) => `${w} में ${c} की शिकायत को ठीक हुआ बताया गया है। क्या समस्या सच में ठीक हुई?`, yes: "हाँ, ठीक हो गया", partly: "आंशिक रूप से ठीक", no: "नहीं, ठीक नहीं हुआ", thanks: "धन्यवाद", thanksNote: "आपका उत्तर दर्ज हो गया। कुछ भी दोबारा खोलने से पहले हर मामले की समीक्षा एक व्यक्ति करता है।", used: "यह लिंक पहले ही इस्तेमाल हो चुका है।", expired: "यह लिंक समाप्त हो चुका है।" },
  mr: { title: "हे दुरुस्त झाले का?", ask: (c, w) => `${w} मधील ${c} ची तक्रार दुरुस्त झाली म्हणून नोंदवली आहे. समस्या खरोखर दुरुस्त झाली का?`, yes: "होय, दुरुस्त झाले", partly: "अंशतः दुरुस्त", no: "नाही, दुरुस्त झाले नाही", thanks: "धन्यवाद", thanksNote: "तुमचे उत्तर नोंदवले गेले. काहीही पुन्हा उघडण्यापूर्वी प्रत्येक प्रकरणाचा आढावा एक व्यक्ती घेते.", used: "ही लिंक आधीच वापरली गेली आहे.", expired: "ही लिंक कालबाह्य झाली आहे." },
  kn: { title: "ಇದು ಸರಿಪಡಿಸಲಾಗಿದೆಯೇ?", ask: (c, w) => `${w} ನಲ್ಲಿನ ${c} ದೂರನ್ನು ಸರಿಪಡಿಸಲಾಗಿದೆ ಎಂದು ಗುರುತಿಸಲಾಗಿದೆ. ಸಮಸ್ಯೆ ನಿಜವಾಗಿಯೂ ಸರಿಯಾಯಿತೇ?`, yes: "ಹೌದು, ಸರಿಪಡಿಸಲಾಗಿದೆ", partly: "ಭಾಗಶಃ ಸರಿಪಡಿಸಲಾಗಿದೆ", no: "ಇಲ್ಲ, ಸರಿಪಡಿಸಿಲ್ಲ", thanks: "ಧನ್ಯವಾದಗಳು", thanksNote: "ನಿಮ್ಮ ಉತ್ತರವನ್ನು ದಾಖಲಿಸಲಾಗಿದೆ. ಯಾವುದನ್ನಾದರೂ ಮತ್ತೆ ತೆರೆಯುವ ಮೊದಲು ಒಬ್ಬ ವ್ಯಕ್ತಿ ಪ್ರತಿ ಪ್ರಕರಣವನ್ನು ಪರಿಶೀಲಿಸುತ್ತಾರೆ.", used: "ಈ ಲಿಂಕ್ ಈಗಾಗಲೇ ಬಳಸಲಾಗಿದೆ.", expired: "ಈ ಲಿಂಕ್ ಅವಧಿ ಮುಗಿದಿದೆ." },
};

/** A signed link a citizen opens on a phone: one question, three answers, no account needed. */
export default function Reply() {
  const { token = "" } = useParams();
  const info = useQuery({ queryKey: ["reply", token], queryFn: () => api.replyInfo(token), retry: false });
  const [lang, setLang] = useState<Lang | null>(null);
  const send = useMutation({ mutationFn: (answer: "yes" | "partly" | "no") => api.reply(token, answer, lang ?? "en") });
  const l: Lang = lang ?? (LANGS.some((x) => x.id === info.data?.lang) ? (info.data!.lang as Lang) : "en");
  const t = TEXT[l];

  let body;
  if (info.isPending) body = <Skeleton rows={3} label="Loading" />;
  else if (info.error) {
    const gone = info.error instanceof ApiError && (info.error.status === 404 || info.error.status === 410);
    body = gone ? <p className="auth-note auth-note-warn" role="alert">{t.expired}</p> : <ErrorState error={info.error} onRetry={() => void info.refetch()} />;
  } else if (info.data.status === "expired") body = <p className="auth-note auth-note-warn" role="alert">{t.expired}</p>;
  else if (info.data.status === "answered" && !send.isSuccess) body = <p className="auth-note" role="status">{t.used}</p>;
  else if (send.isSuccess) body = <div role="status"><h2>{t.thanks}</h2><p>{t.thanksNote}</p></div>;
  else body = (
    <>
      <p className="reply-ask">{t.ask(info.data.category.replace(/_/g, " "), info.data.ward)}</p>
      <div className="reply-actions">
        {(["yes", "partly", "no"] as const).map((a) => <button key={a} type="button" className="btn btn-secondary reply-btn" disabled={send.isPending} onClick={() => send.mutate(a)}>{t[a]}</button>)}
      </div>
      {send.error && <p className="field-error" role="alert">{userMessage(send.error)}</p>}
    </>
  );

  return (
    <div className="reply-page">
      <header><Brand /></header>
      <main className="reply-card" lang={l}>
        <h1>{t.title}</h1>
        {body}
        <div className="reply-langs" role="group" aria-label="Language">
          {LANGS.map((x) => <button key={x.id} type="button" className={`chip ${x.id === l ? "is-active" : ""}`} aria-pressed={x.id === l} lang={x.id} onClick={() => setLang(x.id)}>{x.name}</button>)}
        </div>
      </main>
    </div>
  );
}
