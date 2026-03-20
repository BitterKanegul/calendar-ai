import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { Text } from 'react-native-paper';

export interface ExtractedEmailEvent {
  title: string;
  start_date?: string;
  end_date?: string;
  location?: string;
  confidence: 'high' | 'medium' | 'low';
  source_type?: string;
  evidence?: string;
}

interface EmailExtractionComponentProps {
  highConfidence: ExtractedEmailEvent[];
  mediumConfidence: ExtractedEmailEvent[];
  lowConfidence: ExtractedEmailEvent[];
  onAddSelected: (events: ExtractedEmailEvent[]) => void;
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

const TIER_COLORS = {
  high:   { bg: 'rgba(100, 220, 140, 0.15)', border: 'rgba(100, 220, 140, 0.4)', label: '#7fdd9a', badge: 'Confirmed' },
  medium: { bg: 'rgba(255, 200, 80, 0.15)',  border: 'rgba(255, 200, 80, 0.4)',  label: '#ffc850', badge: 'Possible'  },
  low:    { bg: 'rgba(180, 180, 180, 0.10)', border: 'rgba(180, 180, 180, 0.25)',label: '#aaaaaa', badge: 'Mention'   },
};

function EventCard({
  event,
  selected,
  selectable,
  onToggle,
}: {
  event: ExtractedEmailEvent;
  selected: boolean;
  selectable: boolean;
  onToggle?: () => void;
}) {
  const colors = TIER_COLORS[event.confidence];
  return (
    <TouchableOpacity
      onPress={selectable ? onToggle : undefined}
      activeOpacity={selectable ? 0.7 : 1}
      style={[
        styles.card,
        { backgroundColor: colors.bg, borderColor: colors.border },
        selected && styles.cardSelected,
      ]}
    >
      <View style={styles.cardHeader}>
        <Text style={[styles.badge, { color: colors.label }]}>{colors.badge}</Text>
        {selectable && (
          <View style={[styles.checkbox, selected && styles.checkboxChecked]}>
            {selected && <Text style={styles.checkmark}>✓</Text>}
          </View>
        )}
      </View>
      <Text style={styles.eventTitle}>{event.title}</Text>
      {event.start_date ? (
        <Text style={styles.eventDetail}>{formatDate(event.start_date)}</Text>
      ) : null}
      {event.location ? (
        <Text style={styles.eventDetail}>{event.location}</Text>
      ) : null}
      {event.evidence ? (
        <Text style={styles.evidence} numberOfLines={2}>"{event.evidence}"</Text>
      ) : null}
    </TouchableOpacity>
  );
}

export default function EmailExtractionComponent({
  highConfidence,
  mediumConfidence,
  lowConfidence,
  onAddSelected,
}: EmailExtractionComponentProps) {
  // High-confidence pre-selected; medium unchecked; low not selectable
  const [selected, setSelected] = useState<Set<number>>(() => {
    const s = new Set<number>();
    highConfidence.forEach((_, i) => s.add(i));
    return s;
  });

  const allSelectable = [...highConfidence, ...mediumConfidence];

  const toggle = (idx: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const handleAdd = () => {
    const toAdd = allSelectable.filter((_, i) => selected.has(i));
    onAddSelected(toAdd);
  };

  const hasSelectable = allSelectable.length > 0;

  return (
    <View style={styles.container}>
      {highConfidence.length > 0 && (
        <View style={styles.section}>
          <Text style={[styles.sectionLabel, { color: TIER_COLORS.high.label }]}>
            Confirmed Events
          </Text>
          {highConfidence.map((ev, i) => (
            <EventCard
              key={i}
              event={ev}
              selected={selected.has(i)}
              selectable
              onToggle={() => toggle(i)}
            />
          ))}
        </View>
      )}

      {mediumConfidence.length > 0 && (
        <View style={styles.section}>
          <Text style={[styles.sectionLabel, { color: TIER_COLORS.medium.label }]}>
            Possible Meetings
          </Text>
          {mediumConfidence.map((ev, i) => (
            <EventCard
              key={i}
              event={ev}
              selected={selected.has(highConfidence.length + i)}
              selectable
              onToggle={() => toggle(highConfidence.length + i)}
            />
          ))}
        </View>
      )}

      {lowConfidence.length > 0 && (
        <View style={styles.section}>
          <Text style={[styles.sectionLabel, { color: TIER_COLORS.low.label }]}>
            Informal Mentions
          </Text>
          {lowConfidence.map((ev, i) => (
            <EventCard key={i} event={ev} selected={false} selectable={false} />
          ))}
        </View>
      )}

      {hasSelectable && (
        <TouchableOpacity style={styles.addButton} onPress={handleAdd} activeOpacity={0.8}>
          <Text style={styles.addButtonText}>
            Add Selected ({selected.size})
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 10, gap: 10 },
  section: { gap: 6 },
  sectionLabel: { fontSize: 11, fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: 0.8 },
  card: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 10,
    gap: 4,
  },
  cardSelected: { borderWidth: 2 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  badge: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  checkbox: {
    width: 20, height: 20, borderRadius: 4,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.4)',
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: 'rgba(100,220,140,0.6)', borderColor: '#7fdd9a' },
  checkmark: { color: '#fff', fontSize: 12, fontWeight: 'bold' },
  eventTitle: { color: 'rgba(255,255,255,0.95)', fontSize: 13, fontWeight: '600' },
  eventDetail: { color: 'rgba(255,255,255,0.65)', fontSize: 12 },
  evidence: { color: 'rgba(255,255,255,0.45)', fontSize: 11, fontStyle: 'italic', marginTop: 2 },
  addButton: {
    backgroundColor: 'rgba(100,220,140,0.25)',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(100,220,140,0.5)',
    marginTop: 4,
  },
  addButtonText: { color: '#7fdd9a', fontWeight: '700', fontSize: 14 },
});
