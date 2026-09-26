// The research preview's Agent tab: unlock with the research key, then pick a model
// and edit the prompt template and sampling for this browser's replies. Settings live
// in the parent (App.jsx), which sends them as overrides on /responses. Nothing here
// changes what students get.
import { useState } from "react";

export const EMPTY_AGENT_SETTINGS = {
  model: null,
  promptTemplate: null,
  temperature: null,
  maxTokens: null,
  trimReply: true,
};

// The overrides payload for /responses, or null when every setting is at its
// production default (so an untouched research view calls the agent exactly like
// the student view does).
export function buildOverrides(settings, config) {
  if (!config) {
    return null;
  }
  const overrides = {};
  if (settings.model && settings.model !== config.defaults.model) {
    overrides.model = settings.model;
  }
  if (settings.promptTemplate !== null && settings.promptTemplate !== config.prompt_template) {
    overrides.prompt_template = settings.promptTemplate;
  }
  if (settings.temperature !== null) {
    overrides.temperature = settings.temperature;
  }
  if (settings.maxTokens !== null) {
    overrides.max_tokens = settings.maxTokens;
  }
  if (!settings.trimReply) {
    overrides.trim_reply = false;
  }
  return Object.keys(overrides).length ? overrides : null;
}

// Short description of the active overrides for the strip above the composer.
export function describeOverrides(overrides) {
  if (!overrides) {
    return "";
  }
  const parts = [];
  if (overrides.model) parts.push(overrides.model);
  if (overrides.prompt_template) parts.push("edited prompt");
  if (overrides.temperature !== undefined) parts.push(`temperature ${overrides.temperature}`);
  if (overrides.max_tokens !== undefined) parts.push(`${overrides.max_tokens} max tokens`);
  if (overrides.trim_reply === false) parts.push("no trim");
  return parts.join(", ");
}

function parseNumber(value) {
  if (value.trim() === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function UnlockForm({ onUnlock, isUnlocking, error }) {
  const [keyDraft, setKeyDraft] = useState("");
  return (
    <form
      className="lab-unlock"
      onSubmit={(event) => {
        event.preventDefault();
        if (keyDraft.trim()) {
          onUnlock(keyDraft.trim());
        }
      }}
    >
      <label htmlFor="research-key">Research key</label>
      <p className="lab-hint" id="research-key-hint">
        Unlocks model and prompt controls for this browser. Ask the project lead for the key.
      </p>
      <input
        id="research-key"
        type="password"
        autoComplete="off"
        value={keyDraft}
        onChange={(event) => setKeyDraft(event.target.value)}
        aria-describedby="research-key-hint"
        disabled={isUnlocking}
      />
      <button type="submit" className="button-primary" disabled={isUnlocking || !keyDraft.trim()}>
        {isUnlocking ? "Checking…" : "Unlock"}
      </button>
      {error ? (
        <p className="lab-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

export default function ResearchLab({
  config,
  settings,
  onSettingsChange,
  onUnlock,
  isUnlocking,
  unlockError,
  onForgetKey,
}) {
  if (!config) {
    return (
      <div className="lab">
        <UnlockForm onUnlock={onUnlock} isUnlocking={isUnlocking} error={unlockError} />
      </div>
    );
  }

  const update = (patch) => onSettingsChange({ ...settings, ...patch });
  const overrides = buildOverrides(settings, config);
  const template = settings.promptTemplate ?? config.prompt_template;
  const isPromptEdited = template !== config.prompt_template;

  return (
    <div className="lab">
      <p className={`lab-status ${overrides ? "lab-status-custom" : ""}`} role="status">
        {overrides
          ? "Custom settings are on. Your replies are tagged as research and kept out of student data."
          : "Production settings. Replies match what students get."}
      </p>

      <div className="lab-field">
        <label htmlFor="lab-model">Model</label>
        <select
          id="lab-model"
          value={settings.model ?? config.defaults.model}
          onChange={(event) => update({ model: event.target.value })}
        >
          {config.models.map((model) => (
            <option key={model} value={model}>
              {model === config.defaults.model ? `${model} (production)` : model}
            </option>
          ))}
        </select>
        {config.models_error ? <p className="lab-error">{config.models_error}</p> : null}
      </div>

      <div className="lab-row">
        <div className="lab-field">
          <label htmlFor="lab-temperature">Temperature</label>
          <input
            id="lab-temperature"
            type="number"
            min="0"
            max="2"
            step="0.1"
            placeholder="Model default"
            value={settings.temperature ?? ""}
            onChange={(event) => update({ temperature: parseNumber(event.target.value) })}
          />
        </div>
        <div className="lab-field">
          <label htmlFor="lab-max-tokens">Max tokens</label>
          <input
            id="lab-max-tokens"
            type="number"
            min="16"
            max="4096"
            step="1"
            placeholder={String(config.defaults.max_tokens)}
            value={settings.maxTokens ?? ""}
            onChange={(event) => update({ maxTokens: parseNumber(event.target.value) })}
          />
        </div>
      </div>

      <label className="lab-check">
        <input
          type="checkbox"
          checked={settings.trimReply}
          onChange={(event) => update({ trimReply: event.target.checked })}
        />
        Trim replies to bite size, as students get them
      </label>

      <div className="lab-field lab-field-grow">
        <div className="lab-label-row">
          <label htmlFor="lab-prompt">Prompt template</label>
          {isPromptEdited ? (
            <button
              type="button"
              className="lab-link"
              onClick={() => update({ promptTemplate: null })}
            >
              Restore production prompt
            </button>
          ) : null}
        </div>
        <textarea
          id="lab-prompt"
          spellCheck="false"
          value={template}
          onChange={(event) => update({ promptTemplate: event.target.value })}
        />
        <details className="lab-placeholders">
          <summary>Placeholders you can use</summary>
          <dl>
            {Object.entries(config.placeholders).map(([name, description]) => (
              <div key={name}>
                <dt>
                  <code>{`{${name}}`}</code>
                </dt>
                <dd>{description}</dd>
              </div>
            ))}
          </dl>
        </details>
      </div>

      <p className="lab-hint">
        Check-ins from the proactive daemon always use production settings.
      </p>

      <div className="lab-actions">
        <button
          type="button"
          className="lab-link"
          onClick={() => onSettingsChange({ ...EMPTY_AGENT_SETTINGS })}
          disabled={!overrides}
        >
          Reset to production
        </button>
        <button type="button" className="lab-link" onClick={onForgetKey}>
          Forget research key
        </button>
      </div>
    </div>
  );
}
