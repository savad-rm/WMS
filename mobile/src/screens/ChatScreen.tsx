import React, {useState} from 'react';
import {Alert, FlatList, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View} from 'react-native';
import {apiFetch} from '../api/client';
import {Button, ScreenState} from '../components/ui';
import {useLoad} from '../hooks/useLoad';
import {colors, spacing} from '../theme';

type Message = {id: number; message: string; date: string; time: string; sender_name: string; mine: boolean};
export function ChatScreen({route}: any) {
  const {projectId} = route.params;
  const state = useLoad(() => apiFetch<{results: Message[]}>(`/projects/${projectId}/chat/`), [projectId]);
  const [message, setMessage] = useState(''); const [sending, setSending] = useState(false);
  const send = async () => {setSending(true); try {await apiFetch(`/projects/${projectId}/chat/`, {method: 'POST', body: JSON.stringify({message})}); setMessage(''); await state.reload();} catch (reason) {Alert.alert('Message not sent', reason instanceof Error ? reason.message : 'Please try again.');} finally {setSending(false);}};
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  return <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}><FlatList data={state.data?.results ?? []} keyExtractor={item => String(item.id)} contentContainerStyle={styles.list} renderItem={({item}) => <View style={[styles.bubble, item.mine ? styles.mine : styles.theirs]}><Text style={item.mine && {color: '#fff'}}>{item.message}</Text><Text style={[styles.meta, item.mine && {color: '#dfe3ff'}]}>{item.sender_name} · {item.date} {item.time}</Text></View>} ListEmptyComponent={<Text style={styles.empty}>No messages yet. Start the project conversation.</Text>} /><View style={styles.composer}><TextInput style={styles.input} value={message} onChangeText={setMessage} placeholder="Message the project team" multiline /><Button title="Send" onPress={send} loading={sending} disabled={!message.trim()} /></View></KeyboardAvoidingView>;
}
const styles = StyleSheet.create({screen: {flex: 1, backgroundColor: colors.background}, list: {padding: spacing.md, gap: spacing.sm}, bubble: {maxWidth: '82%', padding: spacing.md, borderRadius: 16}, mine: {alignSelf: 'flex-end', backgroundColor: colors.primary, borderBottomRightRadius: 4}, theirs: {alignSelf: 'flex-start', backgroundColor: '#fff', borderBottomLeftRadius: 4}, meta: {fontSize: 10, color: colors.muted, marginTop: spacing.sm}, empty: {color: colors.muted, textAlign: 'center', marginTop: spacing.xl}, composer: {padding: spacing.sm, borderTopWidth: 1, borderColor: colors.border, backgroundColor: '#fff', flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-end'}, input: {flex: 1, maxHeight: 100, minHeight: 46, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12}});
