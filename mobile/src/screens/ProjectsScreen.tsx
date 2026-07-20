import React, {useState} from 'react';
import {FlatList, RefreshControl, StyleSheet, Text, TextInput, View} from 'react-native';
import {apiFetch} from '../api/client';
import {Card, ScreenState, sharedStyles, StatusPill} from '../components/ui';
import {useLoad} from '../hooks/useLoad';
import {Project} from '../types';
import {colors, spacing} from '../theme';

export function ProjectsScreen({navigation}: any) {
  const [query, setQuery] = useState('');
  const state = useLoad(() => apiFetch<{results: Project[]}>('/projects/'), []);
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  const results = (state.data?.results ?? []).filter(item => `${item.name} ${item.project_no} ${item.client_name} ${item.place}`.toLowerCase().includes(query.toLowerCase()));
  return <View style={sharedStyles.screen}><FlatList data={results} keyExtractor={item => String(item.id)} contentContainerStyle={sharedStyles.content}
    refreshControl={<RefreshControl refreshing={state.loading} onRefresh={state.reload} />} ListHeaderComponent={<View style={{gap: spacing.md}}><View><Text style={sharedStyles.title}>Projects</Text><Text style={sharedStyles.subtitle}>Your assigned portfolio</Text></View><TextInput style={styles.search} value={query} onChangeText={setQuery} placeholder="Search project, client or location" placeholderTextColor={colors.muted} /></View>}
    renderItem={({item}) => <Card><View style={sharedStyles.row}><Text style={styles.title} numberOfLines={1}>{item.name}</Text><StatusPill value={item.status} /></View><Text style={sharedStyles.subtitle}>{item.project_no} · {item.client_name}</Text><Text style={styles.place}>{item.place}</Text><Text style={styles.link} onPress={() => navigation.navigate('ProjectDetail', {projectId: item.id, title: item.name})}>Open project →</Text></Card>}
    ListEmptyComponent={<Card><Text style={sharedStyles.subtitle}>No matching projects.</Text></Card>} />
  </View>;
}
const styles = StyleSheet.create({search: {height: 48, borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: '#fff', paddingHorizontal: spacing.md, color: colors.text}, title: {fontWeight: '800', color: colors.primaryDark, flex: 1}, place: {color: colors.text}, link: {color: colors.primary, fontWeight: '700', paddingTop: spacing.sm}});
