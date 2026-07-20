import React from 'react';
import {RefreshControl, ScrollView, StyleSheet, Text, View} from 'react-native';
import {Card, ScreenState, sharedStyles, StatusPill} from '../components/ui';
import {apiFetch} from '../api/client';
import {useLoad} from '../hooks/useLoad';
import {Dashboard} from '../types';
import {colors, spacing} from '../theme';

const labels: Record<string, string> = {projects: 'Projects', ongoing_projects: 'Ongoing', pending_material_requests: 'Material requests', unread_notifications: 'Unread alerts', open_enquiries: 'Open enquiries'};

export function DashboardScreen({navigation}: any) {
  const state = useLoad(() => apiFetch<Dashboard>('/dashboard/'), []);
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  const data = state.data!;
  return <ScrollView style={sharedStyles.screen} contentContainerStyle={sharedStyles.content} refreshControl={<RefreshControl refreshing={state.loading} onRefresh={state.reload} tintColor={colors.primary} />}>
    <View><Text style={sharedStyles.title}>Hello, {data.user.name.split(' ')[0]}</Text><Text style={sharedStyles.subtitle}>{data.user.role} workspace</Text></View>
    <View style={styles.metrics}>{Object.entries(data.metrics).map(([key, value]) => <Card key={key} style={styles.metric}><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{labels[key] ?? key}</Text></Card>)}</View>
    <Text style={sharedStyles.sectionTitle}>Recent projects</Text>
    {data.recent_projects.map(item => <Card key={item.id}><View style={sharedStyles.row}><Text style={styles.projectName}>{item.name}</Text><StatusPill value={item.status} /></View><Text style={sharedStyles.subtitle}>{item.project_no} · {item.place}</Text><Text onPress={() => navigation.navigate('ProjectDetail', {projectId: item.id, title: item.name})} style={styles.link}>View project →</Text></Card>)}
    {!data.recent_projects.length && <Card><Text style={sharedStyles.subtitle}>No projects are assigned yet.</Text></Card>}
  </ScrollView>;
}

const styles = StyleSheet.create({metrics: {flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm}, metric: {width: '48%', minHeight: 100}, metricValue: {fontSize: 28, fontWeight: '900', color: colors.primary}, metricLabel: {color: colors.muted}, projectName: {fontWeight: '700', color: colors.primaryDark, flex: 1}, link: {color: colors.primary, fontWeight: '700', paddingTop: spacing.sm}});
