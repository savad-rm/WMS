import React, {useState} from 'react';
import {Alert, FlatList, RefreshControl, ScrollView, StyleSheet, Text, View} from 'react-native';
import {apiFetch} from '../api/client';
import {Button, Card, Field, ScreenState, sharedStyles, StatusPill} from '../components/ui';
import {useLoad} from '../hooks/useLoad';
import {Enquiry} from '../types';
import {colors, spacing} from '../theme';
import {useAuth} from '../auth/AuthContext';

export function WorkflowScreen({navigation}: any) {
  const {user} = useAuth();
  const state = useLoad(() => apiFetch<{results: Enquiry[]}>('/enquiries/'), []);
  const [showForm, setShowForm] = useState(false); const [title, setTitle] = useState(''); const [clientName, setClientName] = useState(''); const [description, setDescription] = useState(''); const [deadline, setDeadline] = useState(new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 16)); const [saving, setSaving] = useState(false);
  const create = async () => {setSaving(true); try {await apiFetch('/enquiries/', {method: 'POST', body: JSON.stringify({title, client_name: clientName, description, quotation_deadline: new Date(deadline).toISOString()})}); setTitle(''); setClientName(''); setDescription(''); setShowForm(false); await state.reload();} catch (reason) {Alert.alert('Unable to create enquiry', reason instanceof Error ? reason.message : 'Please try again.');} finally {setSaving(false);}};
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  return <FlatList style={sharedStyles.screen} contentContainerStyle={sharedStyles.content} data={state.data?.results ?? []} keyExtractor={item => String(item.id)} refreshControl={<RefreshControl refreshing={state.loading} onRefresh={state.reload} />}
    ListHeaderComponent={<View style={{gap: spacing.md}}><View><Text style={sharedStyles.title}>Enquiry workflow</Text><Text style={sharedStyles.subtitle}>Leads, quotations and approvals</Text></View>{['Admin', 'Marketing Executive'].includes(user?.role ?? '') && <Button title={showForm ? 'Cancel new enquiry' : 'New enquiry'} variant="outline" onPress={() => setShowForm(value => !value)} />}{showForm && <Card><Field label="Enquiry title" value={title} onChangeText={setTitle} /><Field label="Client name" value={clientName} onChangeText={setClientName} /><Field label="Quotation deadline (YYYY-MM-DDTHH:MM)" value={deadline} onChangeText={setDeadline} /><Field label="Description" value={description} onChangeText={setDescription} multiline /><Button title="Create enquiry" onPress={create} loading={saving} disabled={!title || !clientName || Number.isNaN(Date.parse(deadline))} /></Card>}</View>}
    renderItem={({item}) => <Card><View style={sharedStyles.row}><Text style={styles.title}>{item.title}</Text><StatusPill value={item.status} /></View><Text>{item.client_name}</Text><Text style={sharedStyles.subtitle}>{item.assigned_to ? `Estimator: ${item.assigned_to}` : 'Awaiting assignment'}</Text><Text style={styles.link} onPress={() => navigation.navigate('EnquiryDetail', {enquiryId: item.id, title: item.title})}>View enquiry →</Text></Card>}
    ListEmptyComponent={<Card><Text style={sharedStyles.subtitle}>No enquiries are available for your role.</Text></Card>} />;
}

export function EnquiryDetailScreen({route}: any) {
  const {enquiryId} = route.params;
  const state = useLoad(() => apiFetch<{enquiry: Enquiry}>(`/enquiries/${enquiryId}/`), [enquiryId]);
  const [comment, setComment] = useState('');
  const [selectedEstimator, setSelectedEstimator] = useState('');
  const [amount, setAmount] = useState('');
  const [details, setDetails] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    setSaving(true);
    try { await apiFetch(`/enquiries/${enquiryId}/comments/`, {method: 'POST', body: JSON.stringify({comment})}); setComment(''); await state.reload(); }
    catch (reason) { Alert.alert('Unable to comment', reason instanceof Error ? reason.message : 'Please try again.'); }
    finally { setSaving(false); }
  };
  const runAction = async (action: string) => {
    setSaving(true);
    try {
      const body = action === 'assign' ? {estimator_id: selectedEstimator} : action === 'quote' ? {
        amount, details, material_cost: '0', labour_cost: '0', other_cost: '0',
      } : {};
      await apiFetch(`/enquiries/${enquiryId}/actions/${action}/`, {method: 'POST', body: JSON.stringify(body)});
      await state.reload();
      Alert.alert('Workflow updated', 'The new status is visible to the team.');
    } catch (reason) { Alert.alert('Unable to update', reason instanceof Error ? reason.message : 'Please try again.'); }
    finally { setSaving(false); }
  };
  if (!state.data && (state.loading || state.error)) return <ScreenState loading={state.loading} error={state.error} onRetry={state.reload} />;
  const item = state.data!.enquiry;
  return <ScrollView style={sharedStyles.screen} contentContainerStyle={sharedStyles.content}>
    <Card><View style={sharedStyles.row}><Text style={styles.detailTitle}>{item.title}</Text><StatusPill value={item.status} /></View><Text style={styles.title}>{item.client_name}</Text><Text style={sharedStyles.subtitle}>{item.client_email} {item.client_phone}</Text><Text style={sharedStyles.subtitle}>Quotation deadline: {new Date(item.quotation_deadline).toLocaleDateString()}</Text><Text style={styles.description}>{item.description}</Text></Card>
    {!!item.available_actions?.length && <><Text style={sharedStyles.sectionTitle}>Available actions</Text><Card>
      {item.available_actions.includes('assign') && <><Text style={styles.title}>Assign estimator</Text>{item.estimators?.map(person => <Text key={person.id} onPress={() => setSelectedEstimator(String(person.id))} style={[styles.option, selectedEstimator === String(person.id) && styles.selected]}>{person.name}</Text>)}<Button title="Assign enquiry" onPress={() => void runAction('assign')} loading={saving} disabled={!selectedEstimator} /></>}
      {item.available_actions.includes('quote') && <><Field label="Quotation amount" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" /><Field label="Quotation details" value={details} onChangeText={setDetails} multiline /><Button title="Save quotation draft" onPress={() => void runAction('quote')} loading={saving} disabled={!amount} /></>}
      {item.available_actions.filter(action => !['assign', 'quote'].includes(action)).map(action => <Button key={action} title={action.replaceAll('_', ' ')} onPress={() => void runAction(action)} loading={saving} />)}
    </Card></>}
    <Text style={sharedStyles.sectionTitle}>Quotations</Text>{item.quotations?.map(quote => <Card key={quote.id}><View style={sharedStyles.row}><Text style={styles.title}>{quote.quotation_number || `Version ${quote.version}`} · {quote.amount}</Text><StatusPill value={quote.status} /></View><Text>{quote.details}</Text></Card>)}
    <Text style={sharedStyles.sectionTitle}>Files</Text>{item.attachments?.map(file => <Card key={file.id}><Text style={styles.title}>{file.name}</Text><Text style={sharedStyles.subtitle}>{file.is_cad ? '2D CAD drawing · Open in the WMS web CAD viewer' : 'Project attachment'}</Text></Card>)}
    <Text style={sharedStyles.sectionTitle}>Comments</Text>{item.comments?.map(entry => <Card key={entry.id}><Text style={styles.title}>{entry.author}</Text><Text>{entry.comment}</Text><Text style={sharedStyles.subtitle}>{new Date(entry.created_at).toLocaleString()}</Text></Card>)}
    <Card><Field label="Add comment or remark" value={comment} onChangeText={setComment} multiline placeholder="Write an update for the project team" /><Button title="Post comment" onPress={submit} loading={saving} disabled={!comment.trim()} /></Card>
  </ScrollView>;
}
const styles = StyleSheet.create({title: {fontWeight: '700', color: colors.primaryDark, flex: 1}, detailTitle: {fontSize: 20, fontWeight: '900', color: colors.primaryDark, flex: 1}, description: {color: colors.text, lineHeight: 21, marginTop: spacing.sm}, link: {color: colors.primary, fontWeight: '700', paddingTop: spacing.sm}, option: {padding: 12, borderRadius: 8, backgroundColor: colors.background}, selected: {backgroundColor: colors.primarySoft, color: colors.primary, fontWeight: '700'}});
