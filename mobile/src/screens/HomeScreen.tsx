import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  TextInput,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { Text, Avatar, IconButton } from 'react-native-paper';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import MicButton from '../components/MicButton';
import ListComponent from '../components/ListComponent';
import DeleteComponent from '../components/DeleteComponent';
import CreateComponent from '../components/CreateComponent';
import UpdateComponent from '../components/UpdateComponent';
import ConflictResolutionComponent, { ConflictResolutionOption } from '../components/ConflictResolutionComponent';
import EmailExtractionComponent, { ExtractedEmailEvent } from '../components/EmailExtractionComponent';
import SafetyConfirmationComponent from '../components/SafetyConfirmationComponent';
import LeisureSearchComponent, { LeisureEvent } from '../components/LeisureSearchComponent';
import { useCalendarAPI } from '../services/api';
import { getMockResponse } from '../services/mockData'; // SCREENSHOT MOCK — remove before shipping
import { useAuth } from '../contexts/AuthContext';
import { Event, EventCreate } from '../models/event';


// Animated thinking dots component
const ThinkingDots = () => {
  const [dots, setDots] = useState('');

  useEffect(() => {
    const interval = setInterval(() => {
      setDots(prev => {
        if (prev === '...') return '';
        if (prev === '..') return '...';
        if (prev === '.') return '..';
        return '.';
      });
    }, 500);

    return () => clearInterval(interval);
  }, []);

  return <Text style={{ fontSize: 16, lineHeight: 22, color: 'rgba(255, 255, 255, 0.9)' }}>{dots}</Text>;
};

interface ChatMessage {
  id: string;
  type: 'user' | 'ai';
  content: string;
  timestamp: Date;
  eventData?: EventCreate[] | EventCreate;
  events?: Event[];
  updateArguments?: any;
  responseType?: 'text' | 'list' | 'delete' | 'create' | 'update' | 'conflict_resolution' | 'plan_summary' | 'email_extraction' | 'confirmation_required' | 'leisure_search';
  safetyConfirmationType?: 'delete_safety' | 'update_safety';
  safetyEvents?: Array<{ id: string; title: string; startDate?: string }>;
  safetyCompleted?: boolean;
  conflictEvent?: Event[] | Event;
  conflictOptions?: ConflictResolutionOption[];
  conflictResolutionCompleted?: boolean;
  planChanges?: Array<{ action: string; event_title?: string; event_start?: string; detail?: string }>;
  emailHigh?: ExtractedEmailEvent[];
  emailMedium?: ExtractedEmailEvent[];
  emailLow?: ExtractedEmailEvent[];
  leisureEvents?: LeisureEvent[];
}

export default function HomeScreen() {
  const navigation = useNavigation();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: Date.now().toString(),
      type: 'ai',
      content: 'Hello, I am your AI calendar assistant. How can I help you?',
      timestamp: new Date(),
      eventData: undefined,
      events: undefined,
      responseType: 'text',
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [hasUncompletedComponent, setHasUncompletedComponent] = useState(false);
  const { transcribeAudio, addEvents, processText, deleteMultipleEvents, updateEvent } = useCalendarAPI();
  const { user } = useAuth();
  const scrollViewRef = useRef<ScrollView>(null);
  const inputRef = useRef<TextInput>(null);
  
  const addMessage = (type: 'user' | 'ai', content: string, eventData?: EventCreate[] | EventCreate, events?: Event[], responseType: ChatMessage['responseType'] = 'text', updateArguments?: any, conflictEvent?: Event, conflictOptions?: ConflictResolutionOption[], planChanges?: ChatMessage['planChanges'], emailHigh?: ExtractedEmailEvent[], emailMedium?: ExtractedEmailEvent[], emailLow?: ExtractedEmailEvent[], safetyConfirmationType?: ChatMessage['safetyConfirmationType'], safetyEvents?: ChatMessage['safetyEvents']) => {
    const newMessage: ChatMessage = {
      id: Date.now().toString(),
      type,
      content: content ? content.trim() : '',
      timestamp: new Date(),
      eventData,
      events,
      updateArguments,
      responseType,
      conflictEvent,
      conflictOptions,
      conflictResolutionCompleted: false,
      planChanges,
      emailHigh,
      emailMedium,
      emailLow,
      safetyConfirmationType,
      safetyEvents,
      safetyCompleted: false,
    };
    setMessages(prev => [...prev, newMessage]);
  };

  const scrollToBottom = () => {
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  };

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;

    const userMessage = inputText.trim();
    addMessage('user', userMessage);
    setInputText('');
    scrollToBottom();
    await handleProcessText(userMessage)

    // Maintain focus on the input
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);

  };

  const handleProcessText = async (text: string) => {
    setIsThinking(true);
    try {
      const response = getMockResponse(text) ?? await processText(text) // SCREENSHOT MOCK — remove getMockResponse before shipping
    
      if (response && typeof response === 'object' && response.type === 'list' && response.events) {
        addMessage('ai', response.message || 'Here are your events:', undefined, response.events, 'list')
      } else if (response && typeof response === 'object' && response.type === 'delete' && response.events) {
        addMessage('ai', response.message || 'Select the events to delete:', undefined, response.events, 'delete')
        setHasUncompletedComponent(true);
      } else if (response && typeof response === 'object' && response.type === 'create' && response.events) {
        addMessage('ai', response.message || 'Please review the event details:', response.events, undefined, 'create', undefined, response.conflict_events)
        setHasUncompletedComponent(true);
      } else if (response && typeof response === 'object' && response.type === 'update' && response.events) {
        addMessage('ai', response.message || 'Select the events to update:', undefined, response.events, 'update', response.update_arguments, response.update_conflict_event)
        setHasUncompletedComponent(true);
      } else if (response && typeof response === 'object' && response.type === 'conflict_resolution' && response.options) {
        addMessage('ai', response.message || 'A conflict was detected. Please choose an option:', undefined, undefined, 'conflict_resolution', undefined, undefined, response.options)
        setHasUncompletedComponent(true);
      } else if (response && typeof response === 'object' && response.type === 'confirmation_required') {
        const safetyEvts = (response.events || []).map((ev: any) => ({
          id: ev.id,
          title: ev.title,
          startDate: ev.startDate,
        }));
        addMessage('ai', response.message || 'Please confirm this operation.', undefined, undefined, 'confirmation_required', undefined, undefined, undefined, undefined, undefined, undefined, undefined, response.confirmation_type, safetyEvts);
        setHasUncompletedComponent(true);
      } else if (response && typeof response === 'object' && response.type === 'leisure_search') {
        const msg: ChatMessage = {
          id: Date.now().toString(),
          type: 'ai',
          content: response.message || 'Here are the events I found:',
          timestamp: new Date(),
          responseType: 'leisure_search',
          leisureEvents: response.events || [],
        };
        setMessages(prev => [...prev, msg]);
      } else if (response && typeof response === 'object' && response.type === 'email_extraction') {
        addMessage('ai', response.message || 'Here is what I found in your emails:', undefined, undefined, 'email_extraction', undefined, undefined, undefined, undefined, response.high_confidence, response.medium_confidence, response.low_confidence)
      } else if (response && typeof response === 'object' && response.type === 'plan_summary') {
        addMessage('ai', response.message || 'Planning complete.', undefined, undefined, 'plan_summary', undefined, undefined, undefined, response.changes)
      } else {
        // Handle string responses or other types
        const message = typeof response === 'string' ? response : (response?.message || 'Command processed successfully.');
        addMessage('ai', message, undefined, undefined, 'text')
      }
      
      scrollToBottom();
    } catch (error) {
      addMessage('ai', 'Sorry, I couldn\'t process your command. Please try again.');
      scrollToBottom();
    } finally {
      setIsThinking(false);
    }
  }

  const handleVoiceCommand = async (audioUri: string) => {
    setIsProcessing(true);

    try {
      const response = await transcribeAudio(audioUri);
      const userMessage = response.message || 'Voice command processed';
      addMessage('user', userMessage);
      scrollToBottom();
      await handleProcessText(userMessage)

      //await processCommand(userMessage);
    } catch (error) {
      console.error('Error processing voice command:', error);
      addMessage('ai', 'Sorry, I couldn\'t process your voice command. Please try again.');
      scrollToBottom();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDeleteEvent = async (eventIds: string[]) => {
    try {
      const response = await deleteMultipleEvents(eventIds);
      addMessage('ai', response.message || 'Events deleted successfully!', undefined, undefined, 'text');
      scrollToBottom();
    } catch (error) {
      addMessage('ai', 'Events could not be deleted. Please try again.', undefined, undefined, 'text');
      scrollToBottom();
    }
  };

  const handleCreateEvent = async (eventData: EventCreate[]) => {
    try {
      await addEvents(eventData);
      addMessage('ai', 'Event created successfully!', undefined, undefined, 'text');
      scrollToBottom();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Event could not be created. Please try again.'
      addMessage('ai', message, undefined, undefined, 'text');
      scrollToBottom();
    }
  };

  const handleUpdateEvent = async (eventId: string, updatedEvent: any) => {
    try {
      await updateEvent(eventId, updatedEvent);
      addMessage('ai', 'Event updated successfully!', undefined, undefined, 'text');
      scrollToBottom();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Event could not be updated. Please try again.'
      addMessage('ai', message, undefined, undefined, 'text');
      scrollToBottom();
    }
  };

  const handleAddEmailEvents = async (events: ExtractedEmailEvent[]) => {
    if (!events.length) return;
    try {
      const eventsToCreate = events
        .filter(ev => ev.start_date)
        .map(ev => ({
          title: ev.title,
          startDate: new Date(ev.start_date!),
          location: ev.location,
        }));
      if (eventsToCreate.length) {
        await addEvents(eventsToCreate as any);
      }
      const skipped = events.length - eventsToCreate.length;
      const msg = eventsToCreate.length
        ? `Added ${eventsToCreate.length} event${eventsToCreate.length > 1 ? 's' : ''} from your emails!${skipped ? ` (${skipped} skipped — no date found)` : ''}`
        : 'No events could be added — dates were missing.';
      addMessage('ai', msg, undefined, undefined, 'text');
      scrollToBottom();
    } catch (error: any) {
      addMessage('ai', error.response?.data?.detail || 'Could not add the selected events. Please try again.', undefined, undefined, 'text');
      scrollToBottom();
    }
  };

  const handleAddLeisureEvents = async (events: LeisureEvent[]) => {
    if (!events.length) return;
    try {
      const eventsToCreate = events
        .filter(ev => ev.start_date)
        .map(ev => ({
          title: ev.title,
          startDate: new Date(ev.start_date!),
          duration: ev.duration || 120,
          location: ev.venue_name ? `${ev.venue_name}${ev.city ? ', ' + ev.city : ''}` : ev.city,
        }));
      if (eventsToCreate.length) {
        await addEvents(eventsToCreate as any);
      }
      const msg = eventsToCreate.length
        ? `Added ${eventsToCreate.length} event${eventsToCreate.length > 1 ? 's' : ''} to your calendar!`
        : 'No events could be added — dates were missing.';
      addMessage('ai', msg, undefined, undefined, 'text');
      scrollToBottom();
    } catch (error: any) {
      addMessage('ai', error.response?.data?.detail || 'Could not add the selected events. Please try again.', undefined, undefined, 'text');
      scrollToBottom();
    }
  };

  const handleSafetyConfirm = async (messageId: string) => {
    setMessages(prev => prev.map(msg =>
      msg.id === messageId ? { ...msg, safetyCompleted: true } : msg
    ));
    setHasUncompletedComponent(false);
    addMessage('user', 'Yes, proceed');
    scrollToBottom();
    await handleProcessText('yes');
  };

  const handleSafetyCancel = async (messageId: string) => {
    setMessages(prev => prev.map(msg =>
      msg.id === messageId ? { ...msg, safetyCompleted: true } : msg
    ));
    setHasUncompletedComponent(false);
    addMessage('user', 'Cancel');
    scrollToBottom();
    await handleProcessText('no');
  };

  const handleConflictResolutionChoice = async (messageId: string, optionNum: number) => {
    // Mark this message's conflict resolution as completed
    setMessages(prev => prev.map(msg =>
      msg.id === messageId ? { ...msg, conflictResolutionCompleted: true } : msg
    ));
    setHasUncompletedComponent(false);

    const choiceText = String(optionNum);
    addMessage('user', `Option ${optionNum}`);
    scrollToBottom();
    await handleProcessText(choiceText);
  };

  // Function to mark component as completed
  const markComponentAsCompleted = () => {
    setHasUncompletedComponent(false);
  };

  const renderMessage = (message: ChatMessage) => {
    const isUser = message.type === 'user';

    return (
      <View key={message.id} style={[styles.messageContainer, isUser ? styles.userMessage : styles.aiMessage]}>
        <View style={[styles.messageBubble, isUser ? styles.userBubble : styles.aiBubble]}>
          <Text style={[styles.messageText, isUser ? styles.userMessageText : styles.aiMessageText]}>
            {message.content}
          </Text>

          {message.responseType === 'list' && message.events && (
            <ListComponent 
              events={message.events} 
            />
          )}

          {message.responseType === 'delete' && message.events && (
            <DeleteComponent 
              events={message.events}
              onDelete={handleDeleteEvent}
              onCompleted={markComponentAsCompleted}
            />
          )}

          {message.responseType === 'create' && message.eventData && (
            <CreateComponent 
              eventData={message.eventData as unknown as EventCreate[]}
              onCreate={handleCreateEvent}
              onCompleted={markComponentAsCompleted}
              conflictEvents={message.conflictEvent as any}
            />
          )}

          {message.responseType === 'update' && message.events && (
            <UpdateComponent
              events={message.events}
              updateArguments={message.updateArguments || {}}
              onUpdate={handleUpdateEvent}
              onCompleted={markComponentAsCompleted}
              conflictEvent={message.conflictEvent as any}
            />
          )}

          {message.responseType === 'leisure_search' && message.leisureEvents && (
            <LeisureSearchComponent
              events={message.leisureEvents}
              onAddSelected={handleAddLeisureEvents}
            />
          )}

          {message.responseType === 'email_extraction' && (
            <EmailExtractionComponent
              highConfidence={message.emailHigh || []}
              mediumConfidence={message.emailMedium || []}
              lowConfidence={message.emailLow || []}
              onAddSelected={handleAddEmailEvents}
            />
          )}

          {message.responseType === 'confirmation_required' && message.safetyConfirmationType && !message.safetyCompleted && (
            <SafetyConfirmationComponent
              message=""
              confirmationType={message.safetyConfirmationType}
              events={message.safetyEvents || []}
              onConfirm={() => handleSafetyConfirm(message.id)}
              onCancel={() => handleSafetyCancel(message.id)}
            />
          )}

          {message.responseType === 'conflict_resolution' && message.conflictOptions && (
            <ConflictResolutionComponent
              options={message.conflictOptions}
              onChoose={(optionNum) => handleConflictResolutionChoice(message.id, optionNum)}
              completed={message.conflictResolutionCompleted}
            />
          )}

          {message.responseType === 'plan_summary' && message.planChanges && message.planChanges.length > 0 && (
            <View style={{ marginTop: 8, gap: 4 }}>
              {message.planChanges.map((ch, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 6 }}>
                  <Text style={{ color: ch.action === 'created' ? '#a8f0c6' : ch.action === 'deleted' ? '#f0a8a8' : '#a8d0f0', fontSize: 11, fontWeight: 'bold', minWidth: 52 }}>
                    {ch.action.toUpperCase()}
                  </Text>
                  <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12, flex: 1 }}>
                    {ch.event_title || '—'}{ch.event_start ? ` · ${new Date(ch.event_start).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}` : ''}{ch.detail ? ` (${ch.detail})` : ''}
                  </Text>
                </View>
              ))}
            </View>
          )}

        </View>
      </View>
    );
  };

  return (
    <LinearGradient
      colors={['#667eea', '#764ba2']}
      style={styles.container}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.navigate('Profile' as never)}>
          <View style={styles.userInfo}>
            <Avatar.Text
              size={40}
              label={user?.name?.charAt(0)?.toUpperCase() || 'U'}
              style={styles.avatar}
            />
            <View style={styles.userText}>
              <Text style={styles.userName}>{user?.name || 'User'}</Text>
            </View>
          </View>
        </TouchableOpacity>
        <IconButton
          icon="calendar"
          iconColor="white"
          size={24}
          onPress={() => navigation.navigate('Calendar' as never)}
          style={styles.logoutButton}
        />
      </View>

      <KeyboardAvoidingView
        style={styles.chatContainer}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          ref={scrollViewRef}
          style={styles.messagesContainer}
          contentContainerStyle={styles.messagesContent}
          showsVerticalScrollIndicator={false}
        >
          {messages.map(renderMessage)}
          {isThinking && (
            <View style={[styles.messageContainer, styles.aiMessage]}>
              <View style={[styles.messageBubble, styles.aiBubble]}>
                <ThinkingDots />
              </View>
            </View>
          )}
        </ScrollView>

        <View style={styles.inputContainer}>
          <TextInput
            value={inputText}
            onChangeText={setInputText}
            placeholder="Write your command..."
            placeholderTextColor="rgba(255, 255, 255, 0.6)"
            onSubmitEditing={handleSendMessage}
            returnKeyType="send"
            style={[styles.textInput, hasUncompletedComponent && styles.disabledInput]}
            contextMenuHidden={true}
            selectTextOnFocus={false}
            autoCorrect={false}
            autoCapitalize="none"
            editable={!hasUncompletedComponent}
            pointerEvents={hasUncompletedComponent ? "none" : "auto"}
            ref={inputRef}
          />
          <View>
            {inputText.trim() ? (
              <IconButton
                icon="send"
                iconColor="white"
                size={20}
                onPress={handleSendMessage}
                style={[styles.sendButton, hasUncompletedComponent && styles.disabledButton]}
                disabled={hasUncompletedComponent}
              />
            ) : (
              <MicButton
                onRecordingComplete={handleVoiceCommand}
                isProcessing={isProcessing}
                disabled={hasUncompletedComponent}
              />
            )}
          </View>
        </View>
      </KeyboardAvoidingView>

    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 80,
    paddingBottom: 20,
  },
  userInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  avatar: {
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    marginRight: 12,
  },
  userText: {
    flex: 1,
  },
  userName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: 'white',
  },
  logoutButton: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    marginLeft: 10,
  },
  chatContainer: {
    flex: 1,
    borderTopWidth:3,
    borderTopColor:'rgba(255, 255, 255, 0.1)',
    paddingTop: 12
  },
  messagesContainer: {
    flex: 1,
  },
  messagesContent: {
    paddingHorizontal: 8,
    paddingBottom: 20,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop:20,
    paddingBottom: 32,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.1)',
    gap: 8
  },
  textInput: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    borderBottomLeftRadius: 18,
    borderBottomRightRadius: 18,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 14,
    color: 'white',
    borderWidth: 0,
    borderColor: 'transparent',
  },
  disabledInput: {
    opacity: 0.5,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  inputButtons: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  sendButton: {
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    borderRadius: 20,
    width: 40,
    height: 40,
    margin: 0,
    padding:0
  },
  disabledButton: {
    opacity: 0.5,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  messageContainer: {
    marginVertical: 8,
    paddingHorizontal: 8,
  },
  userMessage: {
    alignItems: 'flex-end',
  },
  aiMessage: {
    alignItems: 'flex-start',
  },
  messageBubble: {
    maxWidth: '90%',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 20,
  },
  userBubble: {
    backgroundColor: '#667eea',
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    borderBottomLeftRadius: 4,
  },
  messageText: {
    fontSize: 16,
    lineHeight: 22,
  },
  userMessageText: {
    color: 'white',
  },
  aiMessageText: {
    color: 'rgba(255, 255, 255, 0.9)',
  },
  eventCard: {
    marginTop: 12,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 12,
  },
  eventTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 8,
    color: 'white',
  },
  eventDetail: {
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.8)',
    marginBottom: 4,
  },
}); 