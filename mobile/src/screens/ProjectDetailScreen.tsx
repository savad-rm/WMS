import React from 'react';
import {Alert, RefreshControl, ScrollView, StyleSheet, Text, View} from 'react-native';
import {apiFetch} from '../api/client';
import {Button, Card, ScreenState, sharedStyles, StatusPill} from '../components/ui';
import {useLoad} from '../hooks/useLoad';
import {Project} from '../types';
import {colors, spacing} from '../theme';

type Detail = {project: Project; works: {id: number; category: string; name: string; schedules: {id: number; from_date: string; to_date: string}[]}[]; progress: any[]; materials_required: any[]; material_requests: any[]; material_issues: any[]; team: Record<string, any[]>; capabilities: {site_updates: boolean; approve_material_requests: boolean; chat: boolean}};

export function ProjectDetailScreen({route, navigation}: any) {
  const {projectId} = route.params;
  const state = useLoad(() => apiFetch<Detail>(`/projects/${projectId}/`), [projectId]);
  const decide = async (id: number, decision: 'approve' | 'reject') => {
    try { await apiFetch(`/material-requests/${id}/${decision}/`, {method: 'POST'}); await state.reload(); }
    catch (reason) { Alert.alert('Unable to update', reason instanceof Error ? reason.message : 'Please try again.'); }
  };
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  const data = state.data!;
  return <ScrollView style={sharedStyles.screen} contentContainerStyle={sharedStyles.content} refreshControl={<RefreshControl refreshing={state.loading} onRefresh={state.reload} />}>
    <Card><View style={sharedStyles.row}><Text style={styles.name}>{data.project.name}</Text><StatusPill value={data.project.status} /></View><Text style={sharedStyles.subtitle}>{data.project.project_no} · {data.project.client_name}</Text><Text style={styles.description}>{data.project.description || 'No description provided.'}</Text><View style={styles.facts}><Text>📍 {data.project.place}</Text><Text>📐 {data.project.area || 'Area not set'}</Text><Text>📅 {data.project.start_date || 'Start date not set'}</Text></View></Card>
    <View style={styles.actions}><Button title="Project chat" variant="outline" onPress={() => navigation.navigate('Chat', {projectId, title: data.project.name})} />{data.capabilities.site_updates && <Button title="Add site update" onPress={() => navigation.navigate('SiteUpdate', {projectId, works: data.works})} />}</View>
    <Text style={sharedStyles.sectionTitle}>Scope and schedule</Text>{data.works.map(item => <Card key={item.id}><Text style={styles.itemTitle}>{item.name}</Text><Text style={sharedStyles.subtitle}>{item.category}</Text>{item.schedules.map(row => <Text key={row.id} style={styles.small}>Scheduled {row.from_date} → {row.to_date}</Text>)}</Card>)}
    <Text style={sharedStyles.sectionTitle}>Material requests</Text>{data.material_requests.map(item => <Card key={item.id}><View style={sharedStyles.row}><Text style={styles.itemTitle}>{item.MATERIAL__name}</Text><StatusPill value={item.status} /></View><Text>{item.quantity} {item.MATERIAL__unit} · {item.date}</Text>{data.capabilities.approve_material_requests && item.status.toLowerCase() === 'pending' && <View style={styles.inline}><Button title="Approve" onPress={() => decide(item.id, 'approve')} /><Button title="Reject" variant="danger" onPress={() => decide(item.id, 'reject')} /></View>}</Card>)}
    <Text style={sharedStyles.sectionTitle}>Latest progress</Text>{data.progress.slice(0, 8).map(item => <Card key={item.id}><View style={sharedStyles.row}><Text style={styles.itemTitle}>{item.WORK__workname}</Text><StatusPill value={item.status} /></View><Text>{item.progress}</Text><Text style={sharedStyles.subtitle}>{item.date}</Text></Card>)}
    <Text style={sharedStyles.sectionTitle}>Project team</Text><Card>{Object.entries(data.team).flatMap(([group, people]) => people.map(person => <View key={`${group}-${person.id}`} style={styles.person}><View><Text style={styles.itemTitle}>{person.name}</Text><Text style={sharedStyles.subtitle}>{group.replace('_', ' ')}</Text></View><Text style={styles.small}>{person.phone}</Text></View>))}</Card>
  </ScrollView>;
}
const styles = StyleSheet.create({name: {fontSize: 21, fontWeight: '900', color: colors.primaryDark, flex: 1}, description: {color: colors.text, lineHeight: 21}, facts: {gap: spacing.sm, marginTop: spacing.sm}, actions: {gap: spacing.sm}, itemTitle: {fontWeight: '700', color: colors.primaryDark}, small: {fontSize: 12, color: colors.muted}, inline: {flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm}, person: {flexDirection: 'row', justifyContent: 'space-between', borderBottomWidth: 1, borderColor: colors.border, paddingVertical: spacing.sm}});
