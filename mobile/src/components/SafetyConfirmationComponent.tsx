import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Text } from 'react-native-paper';

interface EventSummary {
  id: string;
  title: string;
  startDate?: string;
}

interface SafetyConfirmationComponentProps {
  message: string;
  confirmationType: 'delete_safety' | 'update_safety';
  events: EventSummary[];
  onConfirm: () => void;
  onCancel: () => void;
}

function formatDate(iso?: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

const TYPE_COLORS = {
  delete_safety: {
    bg: 'rgba(240, 100, 100, 0.12)',
    border: 'rgba(240, 100, 100, 0.4)',
    label: '#f07070',
    confirmBg: 'rgba(240, 80, 80, 0.25)',
    confirmBorder: 'rgba(240, 80, 80, 0.5)',
    confirmText: '#f07070',
    icon: '⚠️',
    heading: 'Confirm Deletion',
  },
  update_safety: {
    bg: 'rgba(255, 200, 80, 0.12)',
    border: 'rgba(255, 200, 80, 0.4)',
    label: '#ffc850',
    confirmBg: 'rgba(255, 180, 0, 0.20)',
    confirmBorder: 'rgba(255, 180, 0, 0.45)',
    confirmText: '#ffc850',
    icon: '✏️',
    heading: 'Confirm Update',
  },
};

export default function SafetyConfirmationComponent({
  message,
  confirmationType,
  events,
  onConfirm,
  onCancel,
}: SafetyConfirmationComponentProps) {
  const colors = TYPE_COLORS[confirmationType];
  const displayEvents = events.slice(0, 5);
  const overflow = events.length - displayEvents.length;

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, borderColor: colors.border }]}>
      <Text style={[styles.heading, { color: colors.label }]}>
        {colors.icon} {colors.heading}
      </Text>

      <Text style={styles.messageText}>{message}</Text>

      {displayEvents.length > 0 && (
        <View style={styles.eventList}>
          {displayEvents.map((ev, i) => (
            <View key={i} style={styles.eventRow}>
              <Text style={styles.eventTitle}>• {ev.title}</Text>
              {ev.startDate ? (
                <Text style={styles.eventDate}>{formatDate(ev.startDate)}</Text>
              ) : null}
            </View>
          ))}
          {overflow > 0 && (
            <Text style={styles.overflow}>… and {overflow} more</Text>
          )}
        </View>
      )}

      <View style={styles.buttonRow}>
        <TouchableOpacity
          style={[styles.button, styles.cancelButton]}
          onPress={onCancel}
          activeOpacity={0.75}
        >
          <Text style={styles.cancelText}>Cancel</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.button,
            { backgroundColor: colors.confirmBg, borderColor: colors.confirmBorder },
          ]}
          onPress={onConfirm}
          activeOpacity={0.75}
        >
          <Text style={[styles.confirmText, { color: colors.confirmText }]}>
            Yes, Proceed
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    marginTop: 10,
    gap: 10,
  },
  heading: {
    fontSize: 13,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  messageText: {
    color: 'rgba(255,255,255,0.85)',
    fontSize: 13,
    lineHeight: 18,
  },
  eventList: {
    gap: 4,
    paddingLeft: 4,
  },
  eventRow: { gap: 1 },
  eventTitle: {
    color: 'rgba(255,255,255,0.80)',
    fontSize: 13,
    fontWeight: '500',
  },
  eventDate: {
    color: 'rgba(255,255,255,0.50)',
    fontSize: 11,
    paddingLeft: 10,
  },
  overflow: {
    color: 'rgba(255,255,255,0.40)',
    fontSize: 11,
    fontStyle: 'italic',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 2,
  },
  button: {
    flex: 1,
    borderRadius: 8,
    paddingVertical: 9,
    alignItems: 'center',
    borderWidth: 1,
  },
  cancelButton: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderColor: 'rgba(255,255,255,0.2)',
  },
  cancelText: {
    color: 'rgba(255,255,255,0.65)',
    fontWeight: '600',
    fontSize: 13,
  },
  confirmText: {
    fontWeight: '700',
    fontSize: 13,
  },
});
