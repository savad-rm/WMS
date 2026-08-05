import React, {useState} from 'react';
import {Alert, FlatList, RefreshControl, ScrollView, StyleSheet, Text, View} from 'react-native';
import {apiFetch, API_URL, tokenStore} from '../api/client';
import {useAuth} from '../auth/AuthContext';
import {Button, Card, Field, ScreenState, sharedStyles, StatusPill} from '../components/ui';
import {useLoad} from '../hooks/useLoad';
import {colors, spacing} from '../theme';

type Notice = {id: string; date: string; message: string; status: string; type: string; project_name: string};
export function AlertsScreen() {
  const state = useLoad(() => apiFetch<{results: Notice[]}>('/notifications/'), []);
  const markRead = async (id: string) => {await apiFetch(`/notifications/${id}/read/`, {method: 'POST'}); await state.reload();};
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  return <FlatList style={sharedStyles.screen} contentContainerStyle={sharedStyles.content} data={state.data?.results ?? []} keyExtractor={item => String(item.id)} refreshControl={<RefreshControl refreshing={state.loading} onRefresh={state.reload} />} ListHeaderComponent={<View><Text style={sharedStyles.title}>Notifications</Text><Text style={sharedStyles.subtitle}>Operational alerts and project updates</Text></View>} renderItem={({item}) => <Card><View style={sharedStyles.row}><Text style={styles.noticeTitle}>{item.project_name}</Text><StatusPill value={item.status} /></View><Text>{item.message}</Text><Text style={sharedStyles.subtitle}>{item.type} · {item.date}</Text>{item.status.toLowerCase() !== 'read' && <Text onPress={() => void markRead(item.id)} style={styles.link}>Mark as read</Text>}</Card>} ListEmptyComponent={<Card><Text style={sharedStyles.subtitle}>You are all caught up.</Text></Card>} />;
}

export function ProfileScreen() {
  const {user, signOut} = useAuth(); const [current, setCurrent] = useState(''); const [next, setNext] = useState(''); const [saving, setSaving] = useState(false);
  const change = async () => {setSaving(true); try {await apiFetch('/me/', {method: 'PATCH', body: JSON.stringify({current_password: current, new_password: next})}); await tokenStore.clear(); Alert.alert('Password changed', 'Sign in again with your new password.'); await signOut();} catch (reason) {Alert.alert('Unable to change password', reason instanceof Error ? reason.message : 'Please try again.');} finally {setSaving(false);}};
  return <ScrollView style={sharedStyles.screen} contentContainerStyle={sharedStyles.content}><View><Text style={sharedStyles.title}>Profile</Text><Text style={sharedStyles.subtitle}>Account and application settings</Text></View><Card><View style={styles.avatar}><Text style={styles.avatarText}>{user?.name.slice(0, 1).toUpperCase()}</Text></View><Text style={styles.name}>{user?.name}</Text><Text style={styles.center}>{user?.role}</Text><Text style={sharedStyles.subtitle}>{user?.email}</Text><Text style={sharedStyles.subtitle}>{user?.phone} · {user?.place}</Text></Card><Card><Text style={sharedStyles.sectionTitle}>Change password</Text><Field label="Current password" secureTextEntry value={current} onChangeText={setCurrent} /><Field label="New password" secureTextEntry value={next} onChangeText={setNext} /><Button title="Change password" onPress={change} loading={saving} disabled={!current || next.length < 8} /></Card><Card><Text style={sharedStyles.sectionTitle}>Connection</Text><Text style={sharedStyles.subtitle}>{API_URL}</Text></Card><Button title="Sign out" variant="outline" onPress={() => void signOut()} /></ScrollView>;
}
const styles = StyleSheet.create({noticeTitle: {fontWeight: '700', color: colors.primaryDark, flex: 1}, link: {color: colors.primary, fontWeight: '700'}, avatar: {alignSelf: 'center', width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft}, avatarText: {fontSize: 30, fontWeight: '900', color: colors.primary}, name: {textAlign: 'center', fontSize: 20, fontWeight: '800', color: colors.primaryDark}, center: {textAlign: 'center', color: colors.text}});
