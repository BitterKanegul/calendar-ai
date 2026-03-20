import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, Linking } from 'react-native';
import { Text } from 'react-native-paper';

export interface LeisureEvent {
  external_id: string;
  title: string;
  description?: string;
  start_date?: string;
  end_date?: string;
  duration?: number;
  venue_name?: string;
  venue_address?: string;
  city?: string;
  category?: string;
  price_range?: string;
  url?: string;
  image_url?: string;
  fits_free_time: boolean;
}

interface LeisureSearchComponentProps {
  events: LeisureEvent[];
  onAddSelected: (events: LeisureEvent[]) => void;
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

const CATEGORY_COLORS: Record<string, { bg: string; border: string; label: string }> = {
  sports: { bg: 'rgba(80, 160, 255, 0.15)', border: 'rgba(80, 160, 255, 0.4)', label: '#5aa0ff' },
  music:  { bg: 'rgba(160, 100, 255, 0.15)', border: 'rgba(160, 100, 255, 0.4)', label: '#a064ff' },
  arts:   { bg: 'rgba(255, 160, 60, 0.15)',  border: 'rgba(255, 160, 60, 0.4)',  label: '#ffa03c' },
  family: { bg: 'rgba(80, 200, 120, 0.15)',  border: 'rgba(80, 200, 120, 0.4)',  label: '#50c878' },
  film:   { bg: 'rgba(255, 100, 100, 0.15)', border: 'rgba(255, 100, 100, 0.4)', label: '#ff6464' },
  miscellaneous: { bg: 'rgba(180, 180, 180, 0.10)', border: 'rgba(180, 180, 180, 0.25)', label: '#aaaaaa' },
};

function getCategoryColors(category?: string) {
  return CATEGORY_COLORS[category || 'miscellaneous'] || CATEGORY_COLORS.miscellaneous;
}

function EventCard({
  event,
  selected,
  onToggle,
}: {
  event: LeisureEvent;
  selected: boolean;
  onToggle: () => void;
}) {
  const colors = getCategoryColors(event.category);
  return (
    <TouchableOpacity
      onPress={onToggle}
      activeOpacity={0.7}
      style={[
        styles.card,
        { backgroundColor: colors.bg, borderColor: colors.border },
        selected && styles.cardSelected,
      ]}
    >
      <View style={styles.cardHeader}>
        <Text style={[styles.badge, { color: colors.label }]}>
          {(event.category || 'event').toUpperCase()}
        </Text>
        <View style={styles.headerRight}>
          {event.fits_free_time ? (
            <Text style={styles.fitsIndicator}>✓ Free</Text>
          ) : (
            <Text style={styles.busyIndicator}>⚠ Busy</Text>
          )}
          <View style={[styles.checkbox, selected && styles.checkboxChecked]}>
            {selected && <Text style={styles.checkmark}>✓</Text>}
          </View>
        </View>
      </View>
      <Text style={styles.eventTitle}>{event.title}</Text>
      {event.start_date ? (
        <Text style={styles.eventDetail}>{formatDate(event.start_date)}</Text>
      ) : null}
      {event.venue_name ? (
        <Text style={styles.eventDetail}>{event.venue_name}{event.city ? `, ${event.city}` : ''}</Text>
      ) : null}
      {event.price_range ? (
        <Text style={styles.eventDetail}>{event.price_range}</Text>
      ) : null}
      {event.url ? (
        <TouchableOpacity onPress={() => Linking.openURL(event.url!)}>
          <Text style={styles.linkText}>View Details →</Text>
        </TouchableOpacity>
      ) : null}
    </TouchableOpacity>
  );
}

export default function LeisureSearchComponent({
  events,
  onAddSelected,
}: LeisureSearchComponentProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const toggle = (idx: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const handleAdd = () => {
    const toAdd = events.filter((_, i) => selected.has(i));
    onAddSelected(toAdd);
  };

  if (!events.length) return null;

  return (
    <View style={styles.container}>
      {events.map((ev, i) => (
        <EventCard
          key={ev.external_id || i}
          event={ev}
          selected={selected.has(i)}
          onToggle={() => toggle(i)}
        />
      ))}
      {selected.size > 0 && (
        <TouchableOpacity style={styles.addButton} onPress={handleAdd} activeOpacity={0.8}>
          <Text style={styles.addButtonText}>
            Add Selected to Calendar ({selected.size})
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 10, gap: 8 },
  card: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 10,
    gap: 4,
  },
  cardSelected: { borderWidth: 2 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  badge: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  fitsIndicator: { color: '#7fdd9a', fontSize: 11, fontWeight: '600' },
  busyIndicator: { color: '#ffc850', fontSize: 11, fontWeight: '600' },
  checkbox: {
    width: 20, height: 20, borderRadius: 4,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.4)',
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: 'rgba(100,220,140,0.6)', borderColor: '#7fdd9a' },
  checkmark: { color: '#fff', fontSize: 12, fontWeight: 'bold' },
  eventTitle: { color: 'rgba(255,255,255,0.95)', fontSize: 13, fontWeight: '600' },
  eventDetail: { color: 'rgba(255,255,255,0.65)', fontSize: 12 },
  linkText: { color: '#82b1ff', fontSize: 12, fontWeight: '600', marginTop: 4 },
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
