package service

import (
	"context"
	"testing"

	"github.com/ivpn/dns/api/mocks"
	"github.com/ivpn/dns/api/model"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

func TestDeletePasskeyByIDLeavesAuthMethodWhenCredentialsRemain(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	accountID := primitive.NewObjectID()
	credentialID := primitive.NewObjectID()

	store := mocks.NewDb(t)
	svc := &Service{Store: store}

	store.On("GetCredentialByID", mock.Anything, credentialID).Return(&model.Credential{AccountID: accountID}, nil).Once()
	store.On("DeleteCredentialByID", mock.Anything, credentialID, accountID).Return(nil).Once()

	err := svc.DeletePasskeyByID(ctx, credentialID, accountID)
	require.NoError(t, err)

	store.AssertExpectations(t)
	store.AssertNotCalled(t, "GetCredentials", mock.Anything, mock.Anything)
	store.AssertNotCalled(t, "GetAccount", mock.Anything, mock.Anything)
	store.AssertNotCalled(t, "UpdateAccount", mock.Anything, mock.Anything)
}

func TestDeletePasskeyByIDSkipsAccountUpdateWhenLastCredential(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	accountID := primitive.NewObjectID()
	credentialID := primitive.NewObjectID()

	store := mocks.NewDb(t)
	svc := &Service{Store: store}

	store.On("GetCredentialByID", mock.Anything, credentialID).Return(&model.Credential{AccountID: accountID}, nil).Once()
	store.On("DeleteCredentialByID", mock.Anything, credentialID, accountID).Return(nil).Once()

	err := svc.DeletePasskeyByID(ctx, credentialID, accountID)
	require.NoError(t, err)

	store.AssertExpectations(t)
	store.AssertNotCalled(t, "GetCredentials", mock.Anything, mock.Anything)
	store.AssertNotCalled(t, "GetAccount", mock.Anything, mock.Anything)
	store.AssertNotCalled(t, "UpdateAccount", mock.Anything, mock.Anything)
}
