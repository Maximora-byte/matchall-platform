package model

const (
	UpdateOperationRemove  = "remove"
	UpdateOperationAdd     = "add"
	UpdateOperationReplace = "replace"
	UpdateOperationMove    = "move"
	UpdateOperationCopy    = "copy"
	// UpdateOperationTest performs a comparison against the existing value (RFC6902 test)
	UpdateOperationTest = "test"
)
