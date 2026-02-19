import {
  ConfirmModal,
  Field,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { FaMicrophone } from "react-icons/fa";

interface PluginState {
  ip: string;
  port: number;
  tcp_mode: boolean;
  running: boolean;
  pid: number | null;
  status: string;
  attempt: number | null;
  error_code: number | null;
}

interface EditValueModalProps {
  closeModal?: () => void;
  title: string;
  label: string;
  description: string;
  initialValue: string;
  onSubmit: (value: string) => Promise<void>;
}

const getState = callable<[], PluginState>("get_state");
const validateIp = callable<[address: string], boolean>("validate_ip");
const validatePort = callable<[port: number], boolean>("validate_port");
const updateConfig = callable<[address: string, port: number], PluginState>("update_config");
const setTcpMode = callable<[enabled: boolean], PluginState>("set_tcp_mode");
const setEnabled = callable<[enabled: boolean], PluginState>("set_enabled");

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "Unknown error";
}

function EditValueModal({
  closeModal,
  title,
  label,
  description,
  initialValue,
  onSubmit,
}: EditValueModalProps) {
  const [value, setValue] = useState<string>(initialValue);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const close = closeModal ?? (() => {});

  const onConfirm = async () => {
    if (isSaving) {
      return;
    }

    setIsSaving(true);
    try {
      await onSubmit(value.trim());
      close();
    } catch (error) {
      toaster.toast({
        title: "Validation error",
        body: getErrorMessage(error),
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <ConfirmModal
      strTitle={title}
      strOKButtonText="Save"
      strCancelButtonText="Cancel"
      bOKDisabled={isSaving}
      onCancel={close}
      onOK={() => {
        void onConfirm();
      }}
    >
      <div style={{ marginTop: "-0.6rem" }}>
        <TextField
          label={label}
          value={value}
          focusOnMount
          onChange={(event) => setValue(event.currentTarget.value)}
        />
        <div style={{ opacity: 0.8, marginTop: "0.8rem", fontSize: "0.82em" }}>{description}</div>
      </div>
    </ConfirmModal>
  );
}

function Content() {
  const [state, setState] = useState<PluginState | null>(null);
  const [isBusy, setIsBusy] = useState<boolean>(false);

  const refreshState = useCallback(async () => {
    try {
      const next = await getState();
      setState(next);
    } catch {
      // Ignore refresh errors during periodic polling.
    }
  }, []);

  useEffect(() => {
    void refreshState();
    const intervalId = window.setInterval(() => {
      void refreshState();
    }, 1000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [refreshState]);

  const openIpModal = () => {
    if (state === null) {
      return;
    }

    showModal(
      <EditValueModal
        title="Edit IP address"
        label="IP address"
        description="Only valid IPv4 or IPv6 addresses are allowed."
        initialValue={state.ip}
        onSubmit={async (value: string) => {
          const valid = await validateIp(value);
          if (!valid) {
            throw new Error("Enter a valid IPv4 or IPv6 address.");
          }
          const next = await updateConfig(value, state.port);
          setState(next);
        }}
      />,
      undefined,
      {
        popupHeight: 220,
      },
    );
  };

  const openPortModal = () => {
    if (state === null) {
      return;
    }

    showModal(
      <EditValueModal
        title="Edit port"
        label="Port"
        description="Only numeric values in range 1024-65535 are allowed."
        initialValue={String(state.port)}
        onSubmit={async (value: string) => {
          if (!/^\d+$/.test(value)) {
            throw new Error("Port must contain digits only.");
          }

          const port = Number.parseInt(value, 10);
          const valid = await validatePort(port);
          if (!valid) {
            throw new Error("Port must be between 1024 and 65535.");
          }

          const next = await updateConfig(state.ip, port);
          setState(next);
        }}
      />,
      undefined,
      {
        popupHeight: 220,
      },
    );
  };

  const onToggle = async (enabled: boolean) => {
    if (state === null || isBusy) {
      return;
    }

    setIsBusy(true);
    try {
      const next = await setEnabled(enabled);
      setState(next);
    } catch (error) {
      toaster.toast({
        title: "Failed to update AWiM Deck state",
        body: getErrorMessage(error),
      });
      await refreshState();
    } finally {
      setIsBusy(false);
    }
  };

  const onTcpModeToggle = async (enabled: boolean) => {
    if (state === null || isBusy) {
      return;
    }

    setIsBusy(true);
    try {
      const next = await setTcpMode(enabled);
      setState(next);
    } catch (error) {
      toaster.toast({
        title: "Failed to update TCP Mode",
        body: getErrorMessage(error),
      });
      await refreshState();
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <PanelSection title="AWiM Deck">
      <PanelSectionRow>
        <Field
          label="IP address"
          description="Tap to edit."
          highlightOnFocus
          focusable
          onClick={openIpModal}
          onActivate={openIpModal}
        >
          <div>{state?.ip ?? "Loading..."}</div>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field
          label="Port"
          description="Tap to edit."
          highlightOnFocus
          focusable
          onClick={openPortModal}
          onActivate={openPortModal}
        >
          <div>{state?.port ?? "Loading..."}</div>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Status">
          <div>{state?.status ?? "Loading..."}</div>
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="TCP Mode"
          description="Adds --tcp-mode when launching awim. Applies on next start."
          checked={state?.tcp_mode ?? false}
          disabled={state === null || isBusy}
          onChange={(enabled) => {
            void onTcpModeToggle(enabled);
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Enable AWiM Deck"
          description="Runs or stops awim with selected IP and port."
          checked={state?.running ?? false}
          disabled={state === null || isBusy}
          onChange={(enabled) => {
            void onToggle(enabled);
          }}
        />
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  return {
    name: "AWiM Deck",
    titleView: <div className={staticClasses.Title}>AWiM Deck</div>,
    content: <Content />,
    icon: <FaMicrophone />,
    onDismount() {
      return;
    },
  };
});
