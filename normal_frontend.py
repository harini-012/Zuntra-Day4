import { useRef, useState, useEffect } from "react";

const API = "http://127.0.0.1:5000";

const LANGUAGES = [
  { code: "en-IN", label: "English" },
  { code: "ta-IN", label: "Tamil" },
  { code: "hi-IN", label: "Hindi" },
  { code: "te-IN", label: "Telugu" },
  { code: "kn-IN", label: "Kannada" },
];

export default function App() {

  // =========================================
  // STATIC USER
  // =========================================

  const userId = 51;

  const [message, setMessage] = useState("");

  const [messages, setMessages] = useState([
    {
      type: "bot",
      text: "Welcome to Real Estate AI Assistant",
    },
  ]);

  const [selectedLang, setSelectedLang] = useState("en-IN");

  const [isListening, setIsListening] = useState(false);

  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages]);

  // =========================================
  // SEND MESSAGE
  // =========================================

  async function sendMessage(customText = null) {

    const text = customText || message;

    if (!text.trim()) return;

    setMessages((prev) => [
      ...prev,
      {
        type: "user",
        text,
      },
    ]);

    setMessage("");

    try {

      const res = await fetch(`${API}/voice-reply`, {

        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify({
          userId,
          message: text,
        }),
      });

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          type: "bot",
          text: data.reply,
        },
      ]);

      // =========================================
      // PLAY AUDIO
      // =========================================

      if (data.audio) {

        const audio = new Audio(
          `${API}${data.audio}`
        );

        audio.play();
      }

    } catch (err) {

      setMessages((prev) => [
        ...prev,
        {
          type: "bot",
          text: "Server Error",
        },
      ]);
    }
  }

  // =========================================
  // VOICE INPUT
  // =========================================

  function startVoice() {

    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) {

      alert("Voice not supported");

      return;
    }

    const recognition = new SpeechRecognition();

    recognition.lang = selectedLang;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognition.onresult = (event) => {

      const text =
        event.results[0][0].transcript;

      sendMessage(text);
    };

    recognition.start();
  }

  // =========================================
  // UI
  // =========================================

  return (
    <div style={styles.page}>

      {/* HEADER */}

      <div style={styles.header}>
        <h2>Real Estate AI</h2>

        <select
          style={styles.select}
          value={selectedLang}
          onChange={(e) =>
            setSelectedLang(e.target.value)
          }
        >
          {LANGUAGES.map((lang) => (
            <option
              key={lang.code}
              value={lang.code}
            >
              {lang.label}
            </option>
          ))}
        </select>
      </div>

      {/* CHAT AREA */}

      <div style={styles.chatArea}>

        {messages.map((msg, index) => (

          <div
            key={index}
            style={{
              textAlign:
                msg.type === "user"
                  ? "right"
                  : "left",

              marginBottom: 15,
            }}
          >

            <div
              style={
                msg.type === "user"
                  ? styles.userMsg
                  : styles.botMsg
              }
            >
              {msg.text}
            </div>

          </div>
        ))}

        <div ref={bottomRef} />

      </div>

      {/* INPUT */}

      <div style={styles.inputArea}>

        <input
          style={styles.input}
          value={message}
          placeholder="Ask about properties, visits, PG, roommate..."
          onChange={(e) =>
            setMessage(e.target.value)
          }
          onKeyDown={(e) =>
            e.key === "Enter" &&
            sendMessage()
          }
        />

        <button
          style={styles.mic}
          onClick={startVoice}
        >
          {isListening ? "Listening..." : "🎤"}
        </button>

        <button
          style={styles.send}
          onClick={() => sendMessage()}
        >
          Send
        </button>

      </div>
    </div>
  );
}

// =========================================
// STYLES
// =========================================

const styles = {

  page: {
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    background: "#0E0E12",
    color: "white",
  },

  header: {
    padding: 15,
    borderBottom: "1px solid #333",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },

  chatArea: {
    flex: 1,
    overflowY: "auto",
    padding: 20,
  },

  userMsg: {
    display: "inline-block",
    background: "#C9A84C",
    color: "#111",
    padding: 12,
    borderRadius: 10,
    maxWidth: "70%",
  },

  botMsg: {
    display: "inline-block",
    background: "#1E1E24",
    color: "white",
    padding: 12,
    borderRadius: 10,
    maxWidth: "70%",
  },

  inputArea: {
    display: "flex",
    padding: 10,
    gap: 10,
    borderTop: "1px solid #333",
  },

  input: {
    flex: 1,
    padding: 12,
    borderRadius: 10,
    border: "1px solid #333",
    background: "#1E1E24",
    color: "white",
  },

  send: {
    padding: "0 20px",
    borderRadius: 10,
    border: "none",
    background: "#C9A84C",
    cursor: "pointer",
  },

  mic: {
    padding: "0 15px",
    borderRadius: 10,
    border: "1px solid #333",
    background: "#1E1E24",
    color: "white",
    cursor: "pointer",
  },

  select: {
    background: "#1E1E24",
    color: "white",
    border: "1px solid #333",
    borderRadius: 8,
    padding: 8,
  },
};
