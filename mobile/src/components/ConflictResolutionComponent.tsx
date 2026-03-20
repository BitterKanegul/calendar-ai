import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Text } from 'react-native-paper';

export interface ConflictResolutionOption {
  option_num: number;
  description: string;
  action: string;
}

interface ConflictResolutionComponentProps {
  options: ConflictResolutionOption[];
  onChoose: (optionNum: number, description: string) => void;
  completed?: boolean;
}

export default function ConflictResolutionComponent({
  options,
  onChoose,
  completed = false,
}: ConflictResolutionComponentProps) {
  if (completed) return null;

  return (
    <View style={styles.container}>
      {options.map((option) => (
        <TouchableOpacity
          key={option.option_num}
          style={[
            styles.optionCard,
            option.action === 'cancel' && styles.cancelCard,
          ]}
          onPress={() => onChoose(option.option_num, option.description)}
          activeOpacity={0.7}
        >
          <View style={styles.optionNumBadge}>
            <Text style={styles.optionNumText}>{option.option_num}</Text>
          </View>
          <Text style={styles.optionDescription}>{option.description}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 10,
    gap: 8,
  },
  optionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    gap: 10,
  },
  cancelCard: {
    backgroundColor: 'rgba(255, 100, 100, 0.15)',
    borderColor: 'rgba(255, 100, 100, 0.3)',
  },
  optionNumBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255, 255, 255, 0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionNumText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 13,
  },
  optionDescription: {
    flex: 1,
    color: 'rgba(255, 255, 255, 0.9)',
    fontSize: 13,
    lineHeight: 18,
  },
});
