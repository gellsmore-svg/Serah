# Privacy

Serah is for personal conversational history. The default is a SQLite file on the machine that runs it, and the HTTP server binds to `127.0.0.1`.

The public repository must not contain:

- ChatGPT or other message exports
- production SQLite databases
- vector indexes, caches, or checkpoints that hold text
- API responses that quote messages
- API keys, `.env`, or personal logs
- model weights

`.gitignore` excludes those paths. `.env.example` has names only. Synthetic text lives in `src/serah/synthetic.py` and is fictional.

Import warnings record an id and a short reason, not the message body. Application logs are not given the evidence text. The local UI does show the text, because a graph point has to be traceable. Do not expose `serah serve` beyond loopback if the database holds a real history.

Annotations and self-ratings are stored beside observations and are not mixed into them.

Configuring Jev, Kai, Decider, Laya, or an LLM sends evidence to that provider when you score or curate. The mock path does not. Leave those variables unset unless you intend the call.

If a database was created by mistake inside the repository, it matches `*.sqlite` and `.serah/` and should stay untracked. Do not force-add it.
